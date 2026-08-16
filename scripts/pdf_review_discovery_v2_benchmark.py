from __future__ import annotations

import json
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_pipeline import discover_validated_review_pdfs


QA_PRODUCTS = (
    ProductIdentity(model="JBLQ350WLBLKAM", mpn="JBLQ350WLBLKAM"),
    ProductIdentity(model="JBLENDURRUN3BTBAM", mpn="JBLENDURRUN3BTBAM"),
    ProductIdentity(model="JBLT530CBLKAM", mpn="JBLT530CBLKAM"),
)


@dataclass
class ProductBenchmark:
    product: str
    elapsed_seconds: float
    resolved_brand: str | None
    resolved_model: str | None
    resolved_mpn: str | None
    official_domain: str | None
    identity_status: str
    identity_diagnostics: dict
    discovered: int
    downloaded: int
    validated: int
    rejected: int
    duplicates: int
    candidates: list[dict]
    diagnostic_log: list[str]
    gate_failures: list[str]


def _candidate_payload(row) -> dict:
    candidate = row.candidate
    inspection = row.inspection
    provenance = candidate.provenance
    return {
        "url": candidate.url,
        "final_url": inspection.final_url,
        "title": candidate.title,
        "type": candidate.document_type,
        "likely_official": candidate.likely_official,
        "identity_status": candidate.identity_status,
        "identity_reason": inspection.identity_reason,
        "provenance_parent": str(getattr(provenance, "parent_url", "") or ""),
        "provenance_authority": str(getattr(provenance, "parent_authority", "") or ""),
        "pages": inspection.page_count,
        "sha256": row.sha256,
    }


def _generic_failures(identity: ProductIdentity, result, candidates: list[dict]) -> list[str]:
    failures: list[str] = []
    resolved = result.resolved.identity
    strong = str(identity.mpn or identity.gtin or identity.ean or identity.upc or "").strip().lower()
    resolved_model = str(resolved.model or resolved.product_name or "").strip().lower()

    if not resolved.brand:
        failures.append("BRAND_NOT_RESOLVED")
    if not resolved_model or (strong and resolved_model == strong):
        failures.append("DESCRIPTIVE_MODEL_NOT_RESOLVED")
    if result.downloaded_count < result.validated_count:
        failures.append("VALIDATED_WITHOUT_DOWNLOAD")
    if result.validated_count != len(candidates):
        failures.append("VALIDATED_COUNT_MISMATCH")
    for candidate in candidates:
        if int(candidate["pages"] or 0) > 10:
            failures.append("PAGE_LIMIT_BYPASSED")
        if candidate["provenance_parent"] and candidate["provenance_authority"].upper() != "MANUFACTURER":
            failures.append("UNTRUSTED_PROVENANCE_SURFACED")
    return sorted(set(failures))


def run() -> dict:
    products: list[ProductBenchmark] = []
    with tempfile.TemporaryDirectory(prefix="pi-real-pdf-review-") as tmp:
        root = Path(tmp)
        for identity in QA_PRODUCTS:
            diagnostics: list[str] = []
            started = time.perf_counter()
            result = discover_validated_review_pdfs(
                identity,
                root / str(identity.mpn),
                limit=8,
                timeout=10,
                log=diagnostics.append,
            )
            elapsed = time.perf_counter() - started
            candidates = [_candidate_payload(row) for row in result.candidates]
            failures = _generic_failures(identity, result, candidates)

            if identity.mpn == "JBLQ350WLBLKAM" and not candidates:
                failures.append("KNOWN_PRODUCT_ZERO_VALIDATED_PDFS")

            resolved = result.resolved.identity
            products.append(
                ProductBenchmark(
                    product=str(identity.mpn),
                    elapsed_seconds=round(elapsed, 3),
                    resolved_brand=resolved.brand,
                    resolved_model=resolved.model or resolved.product_name,
                    resolved_mpn=resolved.mpn,
                    official_domain=result.resolved.official_domain,
                    identity_status=result.resolved.status,
                    identity_diagnostics=dict(result.resolved.diagnostics or {}),
                    discovered=result.discovered_count,
                    downloaded=result.downloaded_count,
                    validated=result.validated_count,
                    rejected=result.rejected_count,
                    duplicates=result.duplicate_count,
                    candidates=candidates,
                    diagnostic_log=diagnostics[-30:],
                    gate_failures=sorted(set(failures)),
                )
            )

    report = {
        "status": "PASS" if all(not row.gate_failures for row in products) else "FAIL",
        "input_mode": "real_excel_mpn_only",
        "discovery_contract": {
            "download_before_review": True,
            "validate_before_surface": True,
            "ocr_before_review": 0,
            "mistral_before_review": 0,
            "max_review_pdf_pages": 10,
        },
        "products": [asdict(row) for row in products],
        "totals": {
            "discovered": sum(row.discovered for row in products),
            "downloaded": sum(row.downloaded for row in products),
            "validated": sum(row.validated for row in products),
            "rejected": sum(row.rejected for row in products),
            "duplicates": sum(row.duplicates for row in products),
        },
    }
    print("REAL_EXCEL_PDF_REVIEW_BENCHMARK=" + json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(1)
    return report


if __name__ == "__main__":
    run()
