from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import extract_page_offers
from product_intelligence.price_identity_resolution import resolve_price_identity
from product_intelligence.price_peru_coverage import (
    _general_retail_query_specs,
    _is_pdp,
    _search_with_metrics,
    discover_general_peru_retailers,
)
from product_intelligence.price_source_capabilities import detect_ecommerce_platform
from product_intelligence.web_fetch import fetch_page

INPUT = ProductIdentity(mpn="SA400S37/960G")
TARGETS = {
    "EAC": "eac.com.pe",
    "Impacto": "impacto.com.pe",
    "Memory Kings": "memorykings.pe",
    "Supertec": "supertec.com.pe",
}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").casefold().removeprefix("www.")


def _matches(url: str, domain: str) -> bool:
    host = _host(url)
    return host == domain or host.endswith("." + domain)


def _price_signals(html: str) -> list[str]:
    patterns = (
        r"(?:S/\.?|PEN)\s*[0-9][0-9.,]{1,12}",
        r'"(?:price|sellingPrice|salePrice|bestPrice)"\s*:\s*"?[0-9][0-9.,]{1,12}',
    )
    found: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, html, flags=re.IGNORECASE):
            text = str(match).strip()
            if text and text not in found:
                found.append(text)
            if len(found) >= 8:
                return found
    return found


def main() -> int:
    resolution = resolve_price_identity(INPUT, timeout=8, limit_per_query=18)
    identity = resolution.identity
    report: dict = {
        "input_identity": INPUT.model_dump(),
        "resolution": {
            "status": resolution.status,
            "confidence": resolution.confidence,
            "reason": resolution.reason,
            "evidence_backed": resolution.evidence_backed,
            "resolved_brand": identity.brand,
            "resolved_mpn": identity.mpn,
        },
        "brand_mpn_queries": [],
        "sources": {},
    }

    if resolution.status != "RESOLVED" or not resolution.evidence_backed or not str(identity.brand or "").strip():
        report["error"] = "MPN_ONLY_IDENTITY_DID_NOT_RESOLVE_VERIFIED_BRAND"
        Path("p7_micro_gate.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("P7_MICRO_GATE=", json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 2

    specs = _general_retail_query_specs(identity)
    brand_specs = [
        (query, signal)
        for query, signal in specs
        if signal == "VERIFIED_BRAND_MPN_PERU_TLD_SCOPE"
    ]
    if len(brand_specs) != 2:
        report["error"] = f"EXPECTED_2_BRAND_MPN_SCOPES_GOT_{len(brand_specs)}"
        Path("p7_micro_gate.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("P7_MICRO_GATE=", json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 3

    raw_by_query: list[tuple[str, list[str]]] = []
    for query, signal in brand_specs:
        urls, metrics = _search_with_metrics(identity, query, limit=20)
        raw_by_query.append((query, urls))
        report["brand_mpn_queries"].append({
            "query": query,
            "signal_type": signal,
            "raw_results": int(metrics.get("raw_results") or len(urls)),
            "valid_results": int(metrics.get("valid_results") or len(urls)),
            "domains": sorted({_host(url) for url in urls if _host(url)}),
            "urls": urls,
        })

    query_events: list[dict] = []
    admitted = discover_general_peru_retailers(identity, limit=40, on_query_event=query_events.append)

    for label, domain in TARGETS.items():
        raw_hits = [
            url
            for _query, urls in raw_by_query
            for url in urls
            if _matches(url, domain)
        ]
        admitted_hits = [url for url in admitted if _matches(url, domain)]
        pdp_hits = [url for url in admitted_hits if _is_pdp(url, domain, str(identity.mpn or ""))]
        relevant_queries = [
            row for row in query_events
            if domain in str(row.get("query") or "")
            or row.get("signal_type") == "VERIFIED_BRAND_MPN_PERU_TLD_SCOPE"
        ]

        fetched_rows = []
        for url in pdp_hits[:3]:
            try:
                fetched = fetch_page(url, timeout=30, browser_fallback=True, activate_lazy_media=False)
                status_code = getattr(fetched, "status_code", None)
                html = str(getattr(fetched, "html", "") or "")
                final_url = str(getattr(fetched, "final_url", None) or url)
                offers = extract_page_offers(html, final_url, identity, channel=label)
                fetched_rows.append({
                    "url": url,
                    "final_url": final_url,
                    "status_code": status_code,
                    "method": getattr(fetched, "method", None),
                    "platform": detect_ecommerce_platform(final_url, html),
                    "html_bytes": len(html.encode("utf-8", errors="ignore")),
                    "exact_mpn_in_html": str(identity.mpn or "").casefold() in html.casefold(),
                    "price_signals": _price_signals(html),
                    "offers": [offer.to_dict() for offer in offers],
                })
            except Exception as exc:
                fetched_rows.append({"url": url, "error": f"{type(exc).__name__}: {exc}", "offers": []})

        offers = [offer for row in fetched_rows for offer in row.get("offers", [])]
        successful_fetch = next((row for row in fetched_rows if row.get("status_code") and int(row["status_code"]) < 400), None)
        exact_identity = bool(successful_fetch and successful_fetch.get("exact_mpn_in_html"))
        has_price_signal = bool(successful_fetch and successful_fetch.get("price_signals"))

        if offers:
            first_loss = None
            semantic_status = "OFFER_ACCEPTED"
        elif not raw_hits and not admitted_hits:
            first_loss = "DISCOVERY_PROVIDER_COVERAGE"
            semantic_status = "TRUE_MISS"
        elif not pdp_hits:
            first_loss = "DISCOVERY_PDP_NOT_RETURNED_OR_ADMITTED"
            semantic_status = "TRUE_MISS"
        elif not successful_fetch:
            first_loss = "ACCESS_OR_FETCH"
            semantic_status = "DISCOVERED_FETCH_BLOCKED"
        elif not exact_identity:
            first_loss = "IDENTITY"
            semantic_status = "PRODUCT_FOUND_IDENTITY_UNVERIFIED"
        elif has_price_signal:
            first_loss = "PARSER_OR_PRICE_SEMANTICS"
            semantic_status = "PRODUCT_FOUND_PRICE_REJECTED"
        else:
            first_loss = None
            semantic_status = "FOUND_NO_PUBLIC_PRICE"

        report["sources"][label] = {
            "domain": domain,
            "queries_executed": relevant_queries,
            "raw_result": bool(raw_hits or admitted_hits),
            "raw_hits": list(dict.fromkeys(raw_hits)),
            "admitted_urls": admitted_hits,
            "pdp_discovered": bool(pdp_hits),
            "pdp_urls": pdp_hits,
            "fetch": fetched_rows,
            "platform": successful_fetch.get("platform") if successful_fetch else None,
            "identity": "EXACT_MPN" if exact_identity else None,
            "price": [offer.get("selling_price") for offer in offers],
            "first_loss": first_loss,
            "final_semantic_status": semantic_status,
        }

    Path("p7_micro_gate.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("P7_MICRO_GATE=", json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
