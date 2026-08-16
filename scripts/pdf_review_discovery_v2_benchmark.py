from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

from product_intelligence.document_discovery import discover_product_documents
from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_search_trace import PdfSearchTrace


QA_PRODUCTS = (
    ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM"),
    ProductIdentity(brand="JBL", model="Endurance Run 3", mpn="JBLENDURRUN3BTBAM"),
    ProductIdentity(brand="JBL", model="Tune 530C", mpn="JBLT530CBLKAM"),
)


@dataclass
class ProductBenchmark:
    product: str
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
    candidates: list[dict]


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
    }


def run() -> dict:
    products: list[ProductBenchmark] = []
    for identity in QA_PRODUCTS:
        trace = PdfSearchTrace(identity.mpn or identity.model or "product")
        started = time.perf_counter()
        rows = discover_product_documents(identity, limit=10, timeout=10, trace=trace)
        elapsed = time.perf_counter() - started
        summary = trace.summary()
        payload = ProductBenchmark(
            product=str(identity.mpn or identity.model),
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
            candidates=[_candidate_payload(row) for row in rows],
        )
        products.append(payload)

    report = {
        "status": "PASS" if all(row.downloads_before_review == 0 for row in products) else "FAIL",
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
