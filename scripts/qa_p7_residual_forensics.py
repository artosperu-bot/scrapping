from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.parse import urlparse

from product_intelligence import discovery
from product_intelligence.models import ProductIdentity
from product_intelligence.price_identity_resolution import resolve_price_identity
from product_intelligence.price_peru_coverage import (
    _general_retail_query_specs,
    _host,
    _host_matches,
    _is_peru_retail_candidate,
    _required_domain_from_query,
    discover_general_peru_retailers,
)
from product_intelligence.price_source_capabilities import detect_ecommerce_platform
from product_intelligence.price_workflow import (
    _augment_page_rows,
    _channel_from_url,
    _is_trusted_final_offer,
    _parse_page_with_dynamic_retry,
)

INPUT = ProductIdentity(mpn="SA400S37/960G")
# QA oracle labels only. They are never passed into discovery/search as seeds.
TARGETS = {
    "EAC": "eac.com.pe",
    "Memory Kings": "memorykings.pe",
    "Supertec": "supertec.com.pe",
    "Impacto": "impacto.com.pe",
    "NTPeru": "ntperu.com",
    "Gidat": "gidat.pe",
    "Computer House": "computerhouse.pe",
    "UnikStore": "unikstoreperu.com",
    "Sercoplus": "sercoplus.com",
    "Corporacion Luana": "corporacionluana.pe",
}


def _target_matches(url: str, domain: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").casefold().removeprefix("www.")
    return host == domain or host.endswith("." + domain)


def _compact(value: str) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


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
        "query_count": 0,
        "sources": {},
    }
    if resolution.status != "RESOLVED" or not resolution.evidence_backed or not str(identity.brand or "").strip():
        report["error"] = "MPN_ONLY_IDENTITY_DID_NOT_RESOLVE_VERIFIED_BRAND"
        Path("p7_residual_forensics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2

    original_provider = discovery._provider_search
    observed: list[dict] = []
    lock = threading.Lock()

    def observed_provider(query: str, timeout: int):
        rows = original_provider(query, timeout)
        with lock:
            observed.append({"query": query, "timeout": timeout, "rows": rows})
        return rows

    discovery._provider_search = observed_provider
    query_events: list[dict] = []
    try:
        admitted = discover_general_peru_retailers(identity, limit=80, on_query_event=query_events.append)
    finally:
        discovery._provider_search = original_provider

    report["query_count"] = len(observed)
    report["admitted_total"] = len(admitted)
    report["admitted_domains"] = sorted({_host(url) for url in admitted if _host(url)})
    report["brand_mpn_query_count"] = sum(
        1 for query, signal in _general_retail_query_specs(identity)
        if signal == "VERIFIED_BRAND_MPN_PERU_TLD_SCOPE"
    )

    per_query_limit = 20
    for label, domain in TARGETS.items():
        provider_hits: list[dict] = []
        ranked_hits: list[dict] = []
        admission_rejections: list[dict] = []

        for entry in observed:
            query = str(entry["query"])
            raw_rows = list(entry["rows"])
            target_raw = [row for row in raw_rows if _target_matches(row[0], domain)]
            if target_raw:
                provider_hits.append({
                    "query": query,
                    "count": len(target_raw),
                    "urls": list(dict.fromkeys(str(row[0]) for row in target_raw)),
                })

            required = _required_domain_from_query(query)
            domain_rows = discovery._provider_rows_for_domain(raw_rows, required)
            ranked = discovery._rank_candidates(domain_rows, identity, max(per_query_limit * 2, per_query_limit))[:per_query_limit]
            target_ranked = [row.url for row in ranked if _target_matches(row.url, domain)]
            if target_ranked:
                ranked_hits.append({"query": query, "count": len(target_ranked), "urls": target_ranked})
                for url in target_ranked:
                    if not _is_peru_retail_candidate(url, str(identity.mpn or "")):
                        admission_rejections.append({"query": query, "url": url})

        admitted_hits = [url for url in admitted if _target_matches(url, domain)]
        fetch_rows: list[dict] = []
        for url in admitted_hits[:4]:
            channel = _channel_from_url(url)
            events: list[dict] = []

            def emit(event_type: str, **payload):
                events.append({"type": event_type, **payload})

            try:
                html, parsed_rows = _parse_page_with_dynamic_retry(url, identity, channel, emit)
                augmented = _augment_page_rows(url, html, parsed_rows, identity, channel)
                trusted = [row for row in augmented if _is_trusted_final_offer(row)]
                fetch_rows.append({
                    "url": url,
                    "channel": channel,
                    "platform": detect_ecommerce_platform(url, html),
                    "html_bytes": len(html.encode("utf-8", errors="ignore")),
                    "exact_mpn_in_html": _compact(str(identity.mpn or "")) in _compact(html),
                    "parsed_candidates": [row.to_dict() for row in augmented],
                    "trusted_offers": [row.to_dict() for row in trusted],
                    "events": events,
                })
            except Exception as exc:
                fetch_rows.append({
                    "url": url,
                    "channel": channel,
                    "error": f"{type(exc).__name__}: {exc}",
                    "trace_status": getattr(exc, "trace_status", None),
                    "status_code": getattr(exc, "status_code", None),
                    "events": events,
                })

        trusted_offers = [offer for row in fetch_rows for offer in row.get("trusted_offers", [])]
        parsed_candidates = [offer for row in fetch_rows for offer in row.get("parsed_candidates", [])]
        successful_identity_fetch = any(row.get("exact_mpn_in_html") for row in fetch_rows)
        fetch_errors = [row for row in fetch_rows if row.get("error")]

        if trusted_offers:
            first_loss = None
            semantic_status = "OFFER_ACCEPTED"
        elif admitted_hits and fetch_rows and len(fetch_errors) == len(fetch_rows):
            first_loss = "ACCESS_OR_FETCH"
            semantic_status = "DISCOVERED_FETCH_BLOCKED"
        elif admitted_hits and successful_identity_fetch and parsed_candidates:
            first_loss = "PRICE_QUALITY_GATE"
            semantic_status = "PRODUCT_FOUND_PRICE_REJECTED"
        elif admitted_hits and successful_identity_fetch:
            first_loss = "PRICE_NOT_EXTRACTED_OR_NOT_PUBLIC"
            semantic_status = "PRODUCT_FOUND_PRICE_UNRESOLVED"
        elif admitted_hits:
            first_loss = "IDENTITY_OR_PARSER"
            semantic_status = "PRODUCT_DISCOVERED_DOWNSTREAM_UNRESOLVED"
        elif ranked_hits and admission_rejections:
            first_loss = "ADMISSION"
            semantic_status = "TRUE_MISS"
        elif provider_hits and not ranked_hits:
            first_loss = "RANKING"
            semantic_status = "TRUE_MISS"
        elif not provider_hits:
            first_loss = "PROVIDER_COVERAGE"
            semantic_status = "TRUE_MISS"
        else:
            first_loss = "DISCOVERY_UNRESOLVED"
            semantic_status = "TRUE_MISS"

        report["sources"][label] = {
            "domain": domain,
            "provider_hits": provider_hits,
            "ranked_hits": ranked_hits,
            "admission_rejections": admission_rejections,
            "admitted_urls": admitted_hits,
            "fetch": fetch_rows,
            "offer_count": len(trusted_offers),
            "first_loss": first_loss,
            "semantic_status": semantic_status,
        }

    Path("p7_residual_forensics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        name: {
            "provider": bool(row["provider_hits"]),
            "ranked": bool(row["ranked_hits"]),
            "admitted": bool(row["admitted_urls"]),
            "offers": row["offer_count"],
            "first_loss": row["first_loss"],
            "semantic_status": row["semantic_status"],
        }
        for name, row in report["sources"].items()
    }
    print("P7_RESIDUAL_SUMMARY=", json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
