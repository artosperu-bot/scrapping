from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from product_intelligence import document_discovery
from product_intelligence.document_discovery import MAX_LANDING_INSPECTIONS, MAX_QUERY_ATTEMPTS
from product_intelligence.excel_pdf_review_hardening import (
    install as install_excel_pdf_review_hardening,
    prepare_document_identity,
)
from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_search_trace import PdfSearchTrace


# Mirror the real Excel intake: the template exposes a part number in the model
# field, so discovery must bootstrap brand/model/manufacturer itself.
QA_PRODUCTS = (
    ProductIdentity(model="JBLQ350WLBLKAM", mpn="JBLQ350WLBLKAM"),
    ProductIdentity(model="JBLENDURRUN3BTBAM", mpn="JBLENDURRUN3BTBAM"),
    ProductIdentity(model="JBLT530CBLKAM", mpn="JBLT530CBLKAM"),
)


@dataclass
class ProductBenchmark:
    product: str
    resolved_brand: str
    resolved_model: str
    resolved_product_name: str
    official_domain_hint: str
    elapsed_seconds: float
    queries: int
    http_results: int
    browser_results: int
    prefetch_rejected: int
    duplicates: int
    landing_pages: int
    exact_pdps: int
    pdp_pivots: int
    pdf_links: int
    provenance_bound: int
    downloads_before_review: int
    queries_attempted: list[str]
    exact_pdp_urls: list[str]
    landings_inspected: list[str]
    rejected_prefetch: list[dict]
    candidates: list[dict]
    gate_failures: list[str]


def _candidate_payload(row) -> dict:
    provenance = getattr(row, "provenance", None)
    return {
        "url": str(row.url),
        "title": str(row.title or ""),
        "identity_status": str(getattr(row, "identity_status", "UNVERIFIED")),
        "identity_reason": str(getattr(row, "identity_reason", "")),
        "identity_score": int(getattr(row, "identity_score", 0) or 0),
        "likely_official": bool(getattr(row, "likely_official", False)),
        "provenance_parent": str(getattr(provenance, "parent_url", "") or ""),
        "provenance_method": str(getattr(provenance, "discovery_method", "") or ""),
        "provenance_authority": str(getattr(provenance, "parent_authority", "") or ""),
    }


def _event_values(trace: PdfSearchTrace, event: str, key: str) -> list[str]:
    return [str(row.get(key) or "") for row in trace.events if row.get("event") == event and row.get(key)]


def _gate_failures(*, product: str, summary: dict, candidates: list[dict], effective: ProductIdentity) -> list[str]:
    failures: list[str] = []
    if int(summary["queries"]) > MAX_QUERY_ATTEMPTS:
        failures.append(f"QUERY_BUDGET_EXCEEDED:{summary['queries']}>{MAX_QUERY_ATTEMPTS}")
    if int(summary["landing_pages"]) > MAX_LANDING_INSPECTIONS:
        failures.append(f"LANDING_BUDGET_EXCEEDED:{summary['landing_pages']}>{MAX_LANDING_INSPECTIONS}")
    if int(summary["downloads_ok"]) != 0:
        failures.append(f"DOWNLOAD_BEFORE_REVIEW:{summary['downloads_ok']}")
    if not str(effective.brand or "").strip():
        failures.append("IDENTITY_BOOTSTRAP_BRAND_MISSING")
    descriptive = str(effective.model or effective.product_name or "").strip()
    if not descriptive or descriptive.lower() == product.lower():
        failures.append("IDENTITY_BOOTSTRAP_MODEL_MISSING")
    for candidate in candidates:
        if candidate["identity_reason"] == "snippet_only_strong_identifier":
            failures.append("SNIPPET_ONLY_IDENTITY_SURFACED")
        if candidate["provenance_parent"] and candidate["provenance_authority"].upper() != "MANUFACTURER":
            failures.append("THIRD_PARTY_PROVENANCE_SURFACED")

    # Non-vacuous known regression: Quantum 350 has a public official JBL spec sheet.
    if product == "JBLQ350WLBLKAM":
        official = [
            row for row in candidates
            if row["likely_official"]
            and "jbl" in (urlparse(row["url"]).hostname or "").lower()
            and "quantum" in (row["url"] + " " + row["title"]).lower()
            and ("spec" in (row["url"] + " " + row["title"]).lower() or "data" in (row["url"] + " " + row["title"]).lower())
        ]
        if not official:
            failures.append("KNOWN_OFFICIAL_PDF_NOT_FOUND")
    return sorted(set(failures))


def run() -> dict:
    install_excel_pdf_review_hardening()

    products: list[ProductBenchmark] = []
    for identity in QA_PRODUCTS:
        product = str(identity.mpn or identity.model)
        effective, domain = prepare_document_identity(identity, timeout=8)
        trace = PdfSearchTrace(product)
        started = time.perf_counter()
        # Call with the enriched identity explicitly so diagnostics show exactly what
        # the packaged adapter resolved and discovery does not need a second bootstrap.
        rows = document_discovery.discover_product_documents(
            effective,
            limit=10,
            timeout=10,
            trace=trace,
            official_domain=domain,
        )
        elapsed = time.perf_counter() - started
        summary = trace.summary()
        candidates = [_candidate_payload(row) for row in rows]
        failures = _gate_failures(product=product, summary=summary, candidates=candidates, effective=effective)
        payload = ProductBenchmark(
            product=product,
            resolved_brand=str(effective.brand or ""),
            resolved_model=str(effective.model or ""),
            resolved_product_name=str(effective.product_name or ""),
            official_domain_hint=str(domain or ""),
            elapsed_seconds=round(elapsed, 3),
            queries=summary["queries"],
            http_results=summary["http_results"],
            browser_results=summary["browser_results"],
            prefetch_rejected=summary["prefetch_rejected"],
            duplicates=summary["duplicates"],
            landing_pages=summary["landing_pages"],
            exact_pdps=summary["exact_pdps"],
            pdp_pivots=summary["pdp_pivots"],
            pdf_links=summary["pdf_links"],
            provenance_bound=summary["provenance_bound"],
            downloads_before_review=summary["downloads_ok"],
            queries_attempted=_event_values(trace, "PDF_SEARCH_QUERY", "query"),
            exact_pdp_urls=_event_values(trace, "PDF_EXACT_PDP_FOUND", "url"),
            landings_inspected=_event_values(trace, "PDF_LANDING_INSPECTED", "url"),
            rejected_prefetch=[
                {"url": str(row.get("url") or ""), "reason": str(row.get("reason") or "")}
                for row in trace.events
                if row.get("event") == "PDF_CANDIDATE_REJECTED_PRE_FETCH"
            ],
            candidates=candidates,
            gate_failures=failures,
        )
        products.append(payload)

    report = {
        "status": "PASS" if all(not row.gate_failures for row in products) else "FAIL",
        "input_mode": "excel_mpn_only",
        "limits": {
            "max_queries_per_product": MAX_QUERY_ATTEMPTS,
            "max_landings_per_product": MAX_LANDING_INSPECTIONS,
            "downloads_before_review": 0,
            "third_party_provenance": 0,
            "snippet_only_identity_candidates": 0,
        },
        "products": [asdict(row) for row in products],
        "totals": {
            "queries": sum(row.queries for row in products),
            "raw_results": sum(row.http_results + row.browser_results for row in products),
            "prefetch_rejected": sum(row.prefetch_rejected for row in products),
            "duplicates": sum(row.duplicates for row in products),
            "landing_pages": sum(row.landing_pages for row in products),
            "exact_pdps": sum(row.exact_pdps for row in products),
            "pdp_pivots": sum(row.pdp_pivots for row in products),
            "pdf_links": sum(row.pdf_links for row in products),
            "provenance_bound": sum(row.provenance_bound for row in products),
            "downloads_before_review": sum(row.downloads_before_review for row in products),
            "candidates": sum(len(row.candidates) for row in products),
        },
    }
    print("PDF_REVIEW_DISCOVERY_V2_BENCHMARK=" + json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(1)
    return report


if __name__ == "__main__":
    run()
