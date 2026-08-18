from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from unittest.mock import patch

import requests

from product_intelligence import discovery, identity_bootstrap, price_workflow
from product_intelligence.identifiers import validate_gtin
from product_intelligence.models import ProductIdentity

MPN = "SA400S37/960G"
OUTPUT_DIR = Path(os.environ.get("PRICE_AFTER_OUTPUT", "qa_price_after_output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = OUTPUT_DIR / "after_sa400s37_960g.json"

BEFORE = {
    "queries": 58,
    "search_results_raw": 634,
    "unique_raw_search_urls": 393,
    "unique_urls_discovered_admitted": 29,
    "urls_fetched": 29,
    "fetch_failures": 3,
    "parsed_pages": 37,
    "zero_offer_pages": 25,
    "identity_accepted_evaluations": 34,
    "identity_rejected_evaluations": 111,
    "prices_extracted_candidate_offers": 16,
    "prices_rejected_final_quality": 2,
    "offers_accepted": 11,
    "duplicates_removed_final_dedupe": 3,
    "benchmark_confirmed_sources": 23,
    "benchmark_sources_with_offer": 5,
    "false_no_hay_count": 18,
    "false_no_hay_rate": 78.3,
    "identifier_contamination": 6,
    "marketplace_sellers": 1,
}


def _host(url: str | None) -> str:
    return (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")


def _site_domain(query: str) -> str | None:
    match = re.search(r"\bsite:([^\s\"']+)", str(query or ""), re.I)
    if not match:
        return None
    return match.group(1).split("/", 1)[0].lower().removeprefix("www.")


def _offer_dict(row: Any) -> dict[str, Any]:
    return row.to_dict() if hasattr(row, "to_dict") else dict(row)


class Recorder:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.raw_urls: set[str] = set()
        self.query_rows: list[dict[str, Any]] = []
        self.http_requests = 0
        self.page_fetch_calls = 0

    def record_query(self, query: str, rows: list[Any], source: str) -> None:
        urls: list[str] = []
        for row in rows or []:
            if isinstance(row, (tuple, list)) and row:
                value = row[0]
            else:
                value = getattr(row, "url", row)
            url = str(value or "")
            if url.startswith(("http://", "https://")):
                urls.append(url)
        with self.lock:
            new_urls = [url for url in urls if url not in self.raw_urls]
            new_domains = sorted({_host(url) for url in new_urls if _host(url)} - {_host(url) for url in self.raw_urls if _host(url)})
            self.raw_urls.update(urls)
            self.query_rows.append({
                "query": str(query),
                "domain": _site_domain(query),
                "source": source,
                "raw_results": len(urls),
                "new_urls": len(new_urls),
                "new_domains": new_domains,
                "raw_urls": urls,
            })


rec = Recorder()


def _identity_contamination(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for row in offers:
        evidence = dict(row.get("evidence") or {})
        raw_gtin = evidence.get("gtin")
        gtin = str(raw_gtin or "").strip()
        collisions: list[str] = []
        if gtin:
            checked = validate_gtin(gtin)
            if not checked.valid:
                collisions.append(f"invalid_gtin:{checked.reason}")
            compare_fields = {
                "offer.sku": row.get("sku"),
                "offer.seller_sku": row.get("seller_sku"),
                "offer.part_number": row.get("part_number"),
                "offer.publication_id": row.get("publication_id"),
                "offer.marketplace_product_id": row.get("marketplace_product_id"),
                "offer.marketplace_listing_id": row.get("marketplace_listing_id"),
            }
            compact = re.sub(r"\D", "", gtin)
            for name, value in compare_fields.items():
                other = re.sub(r"\D", "", str(value or ""))
                if compact and other and compact == other and str(value or "") != gtin:
                    collisions.append(f"gtin_collides_with_{name}")
        if collisions:
            flags.append({
                "channel": row.get("channel"),
                "url": row.get("url"),
                "gtin": raw_gtin,
                "seller_sku": row.get("seller_sku"),
                "sku": row.get("sku"),
                "marketplace_product_id": row.get("marketplace_product_id"),
                "marketplace_listing_id": row.get("marketplace_listing_id"),
                "collisions": collisions,
            })
    return flags


def _marketplace_report(offers: list[dict[str, Any]], coverage: dict[str, Any]) -> list[dict[str, Any]]:
    names = ("Mercado Libre", "Falabella", "Ripley", "Sodimac", "Plaza Vea")
    result: list[dict[str, Any]] = []
    events = list(coverage.get("events") or [])
    for name in names:
        key = re.sub(r"[^a-z0-9]+", "", name.casefold())
        def matches(channel=None, url=None):
            hay = re.sub(r"[^a-z0-9]+", "", f"{channel or ''} {_host(url)}".casefold())
            hints = {key}
            if name == "Mercado Libre": hints.add("mercadolibre")
            if name == "Plaza Vea": hints.add("plazavea")
            return any(hint in hay for hint in hints)
        rows = [row for row in offers if matches(row.get("channel"), row.get("url"))]
        urls = sorted({str(e.get("url")) for e in events if e.get("url") and matches(e.get("channel"), e.get("url"))})
        result.append({
            "source": name,
            "product_or_catalog_pages": len(urls),
            "urls": urls,
            "catalog_products": len({str(row.get("marketplace_product_id")) for row in rows if row.get("marketplace_product_id")}),
            "listings": len({str(row.get("marketplace_listing_id") or row.get("publication_id")) for row in rows if row.get("marketplace_listing_id") or row.get("publication_id")}),
            "sellers": len({str(row.get("seller_id") or row.get("seller_display_name")) for row in rows if row.get("seller_id") or row.get("seller_display_name")}),
            "offers": len(rows),
        })
    return result


def _funnel_from_coverage(coverage: dict[str, Any], offers: list[dict[str, Any]]) -> dict[str, Any]:
    events = list(coverage.get("events") or [])
    unique = lambda stage: {str(row.get("url")) for row in events if row.get("stage") == stage and row.get("url")}
    stages = [str(row.get("stage") or "") for row in events]
    return {
        "queries": len(rec.query_rows),
        "search_results_raw": sum(int(row.get("raw_results") or 0) for row in rec.query_rows),
        "unique_raw_search_urls": len(rec.raw_urls),
        "unique_urls_discovered_admitted": len(unique("URL_DISCOVERED")),
        "urls_fetched": len(unique("FETCH_OK")),
        "fetch_failures": len(unique("FETCH_FAILED") | unique("FETCH_BLOCKED") | unique("FETCH_TIMEOUT")),
        "parsed_pages": stages.count("PARSER_OK") + stages.count("PARSER_ZERO_OFFERS"),
        "zero_offer_pages": stages.count("PARSER_ZERO_OFFERS"),
        "identity_accepted_evaluations": stages.count("IDENTITY_ACCEPTED"),
        "identity_rejected_evaluations": stages.count("IDENTITY_REJECTED"),
        "prices_extracted_candidate_offers": stages.count("PRICE_EXTRACTED"),
        "prices_rejected_final_quality": stages.count("PRICE_REJECTED"),
        "offers_accepted": len(offers),
        "duplicates_removed_final_dedupe": stages.count("OFFER_DEDUPED"),
    }


def main() -> int:
    identity = ProductIdentity(mpn=MPN)
    run_events: list[dict[str, Any]] = []
    errors: list[str] = []

    original_discovery_provider = discovery._provider_search
    original_bootstrap_provider = identity_bootstrap._provider_search
    original_browser_search = identity_bootstrap.browser_search
    original_session_request = requests.sessions.Session.request
    original_fetch_page = price_workflow.fetch_page

    def observed_discovery_provider(query: str, timeout: int):
        rows = original_discovery_provider(query, timeout)
        rec.record_query(query, rows, "discovery._provider_search")
        return rows

    def observed_bootstrap_provider(query: str, timeout: int):
        rows = original_bootstrap_provider(query, timeout)
        rec.record_query(query, rows, "identity_bootstrap._provider_search")
        return rows

    def observed_browser_search(*args, **kwargs):
        query = str(args[0] if args else kwargs.get("query") or kwargs.get("q") or "")
        rows = original_browser_search(*args, **kwargs)
        rec.record_query(query, rows or [], "identity_bootstrap.browser_search")
        return rows

    def observed_request(self, method, url, *args, **kwargs):
        with rec.lock:
            rec.http_requests += 1
        return original_session_request(self, method, url, *args, **kwargs)

    def observed_fetch_page(url, *args, **kwargs):
        with rec.lock:
            rec.page_fetch_calls += 1
        return original_fetch_page(url, *args, **kwargs)

    started = time.perf_counter()
    offers = []
    try:
        with (
            patch.object(discovery, "_provider_search", observed_discovery_provider),
            patch.object(identity_bootstrap, "_provider_search", observed_bootstrap_provider),
            patch.object(identity_bootstrap, "browser_search", observed_browser_search),
            patch.object(requests.sessions.Session, "request", observed_request),
            patch.object(price_workflow, "fetch_page", observed_fetch_page),
        ):
            offers = price_workflow.run_price_product(identity, OUTPUT_DIR, on_event=run_events.append, max_sources=48)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    runtime = time.perf_counter() - started

    offer_rows = [_offer_dict(row) for row in offers]
    identity_event = next((row for row in run_events if row.get("type") == "identity"), {})
    coverage_event = next((row for row in reversed(run_events) if row.get("type") == "coverage"), {})
    coverage = dict(coverage_event.get("report") or {})
    funnel = _funnel_from_coverage(coverage, offer_rows)
    contamination = _identity_contamination(offer_rows)
    marketplaces = _marketplace_report(offer_rows, coverage)

    query_metrics = list(rec.query_rows)
    trace_query_events = [row for row in coverage.get("events", []) if row.get("stage") in {"QUERY_EXECUTED", "QUERY_INFORMATION_GAIN", "DISCOVERY_STOP", "URL_REJECTED_BY_DOMAIN", "URL_REJECTED_BY_RANKING"}]
    report = {
        "benchmark": "AFTER SA400S37/960G",
        "oracle_blind_during_run": True,
        "input": {"constructor": 'ProductIdentity(mpn="SA400S37/960G")', "provided_fields": {"mpn": MPN}},
        "identity_after": {
            "input_identity": identity_event.get("input_identity") or identity.model_dump(),
            "resolved_identity": identity_event.get("resolved_identity") or identity.model_dump(),
            "status": identity_event.get("status"),
            "confidence": identity_event.get("confidence"),
            "reason": identity_event.get("reason"),
            "official_domain_hint": identity_event.get("official_domain_hint"),
        },
        "funnel": funnel,
        "accepted_offers": offer_rows,
        "coverage": coverage,
        "marketplace_behavior": marketplaces,
        "identifier_contamination": contamination,
        "query_provider_trace": query_metrics,
        "query_information_gain": trace_query_events,
        "performance": {
            "runtime_seconds": runtime,
            "requests_http_calls": rec.http_requests,
            "price_page_fetch_calls": rec.page_fetch_calls,
            "note": "requests_http_calls counts Python requests traffic; browser subresource traffic is not included",
        },
        "run_events": run_events,
        "run_errors": errors,
        "git": {"sha": os.environ.get("GITHUB_SHA"), "ref": os.environ.get("GITHUB_REF")},
    }

    comparison = {
        "before": BEFORE,
        "after": funnel | {
            "identifier_contamination": len(contamination),
            "marketplace_sellers": sum(row["sellers"] for row in marketplaces),
        },
        "delta": {},
        "notes": [
            "23-source oracle comparison is intentionally deferred until after this oracle-blind run.",
            "Raw provider query counts include identity bootstrap and discovery providers, matching the diagnostic intent of BEFORE.",
        ],
    }
    for key, before_value in BEFORE.items():
        after_value = comparison["after"].get(key)
        if isinstance(before_value, (int, float)) and isinstance(after_value, (int, float)):
            comparison["delta"][key] = after_value - before_value

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "identity_after.json").write_text(json.dumps(report["identity_after"], ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "coverage_after.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "query_information_gain.json").write_text(json.dumps({"provider_queries": query_metrics, "trace_events": trace_query_events}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "before_after_comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")

    generated_capabilities = OUTPUT_DIR / "price_intelligence" / "source_capabilities.json"
    if generated_capabilities.is_file():
        (OUTPUT_DIR / "source_capabilities.json").write_text(generated_capabilities.read_text(encoding="utf-8"), encoding="utf-8")

    print("AFTER_REPORT_PATH=", REPORT_PATH)
    print("IDENTITY_AFTER=", json.dumps(report["identity_after"], ensure_ascii=False))
    print("FUNNEL_AFTER=", json.dumps(funnel, ensure_ascii=False))
    print("OFFERS_AFTER=", len(offer_rows))
    print("CONTAMINATION_AFTER=", len(contamination))
    print("MARKETPLACES_AFTER=", json.dumps(marketplaces, ensure_ascii=False))
    print("PERFORMANCE_AFTER=", json.dumps(report["performance"], ensure_ascii=False))
    print("RUN_ERRORS=", json.dumps(errors, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
