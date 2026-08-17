from __future__ import annotations

import json
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from product_intelligence.part_number_pdf_search import search_product_pdfs_by_part_number


QA_PART_NUMBERS = (
    "JBLQ350WLBLKAM",
    "JBLENDURRUN3BTBAM",
    "JBLT530CBLKAM",
)


@dataclass
class ProductBenchmark:
    product: str
    elapsed_seconds: float
    resolved_brand: str | None
    resolved_model: str | None
    official_domain: str | None
    identity_status: str
    identity_diagnostics: dict
    discovered: int
    downloaded: int
    validated: int
    rejected: int
    duplicates: int
    page_limit_rejected: int
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
        "identity_provenance_bound": bool(inspection.identity_provenance_bound),
        "provenance_parent": str(getattr(provenance, "parent_url", "") or ""),
        "provenance_authority": str(getattr(provenance, "parent_authority", "") or ""),
        "pages": inspection.page_count,
        "sha256": row.sha256,
    }


def _cross_product_contamination(part_number: str, candidates: list[dict]) -> bool:
    siblings = {value.lower() for value in QA_PART_NUMBERS if value != part_number}
    for candidate in candidates:
        haystack = " ".join(
            str(candidate.get(key) or "")
            for key in ("url", "final_url", "title", "provenance_parent")
        ).lower()
        if any(sibling in haystack for sibling in siblings):
            return True
    return False


def _failures(part_number: str, result, candidates: list[dict]) -> list[str]:
    failures: list[str] = []
    resolved = result.resolved.identity
    resolved_model = str(resolved.model or resolved.product_name or "").strip().lower()
    if not resolved.brand:
        failures.append("BRAND_NOT_RESOLVED")
    if not resolved_model or resolved_model == part_number.lower():
        failures.append("DESCRIPTIVE_MODEL_NOT_RESOLVED")
    if not str(result.resolved.official_domain or "").strip():
        failures.append("OFFICIAL_DOMAIN_NOT_RESOLVED")
    if result.discovered_count < 1:
        failures.append("PRODUCT_ZERO_DISCOVERED_PDFS")
    if result.downloaded_count < 1:
        failures.append("PRODUCT_ZERO_DOWNLOAD_ATTEMPTS")
    if result.validated_count < 1 or not candidates:
        failures.append("PRODUCT_ZERO_VALIDATED_PDFS")
    if result.validated_count != len(candidates):
        failures.append("VALIDATED_COUNT_MISMATCH")
    if _cross_product_contamination(part_number, candidates):
        failures.append("CROSS_PRODUCT_CONTAMINATION")

    trustworthy = False
    for candidate in candidates:
        if not str(candidate["final_url"] or candidate["url"]).lower().split("?", 1)[0].endswith(".pdf"):
            failures.append("NON_PDF_SURFACED")
        if int(candidate["pages"] or 0) > 10:
            failures.append("PAGE_LIMIT_BYPASSED")
        if candidate["provenance_parent"] and candidate["provenance_authority"].upper() != "MANUFACTURER":
            failures.append("UNTRUSTED_PROVENANCE_SURFACED")
        if candidate["identity_provenance_bound"] and candidate["provenance_authority"].upper() == "MANUFACTURER":
            trustworthy = True
        elif candidate["likely_official"] and str(candidate["identity_status"]).upper() in {"VALIDATED", "PROVENANCE_BOUND", "EXACT"}:
            trustworthy = True
    if candidates and not trustworthy:
        failures.append("NO_TRUSTWORTHY_PRODUCT_PDF")
    return sorted(set(failures))


def run() -> dict:
    products: list[ProductBenchmark] = []
    with tempfile.TemporaryDirectory(prefix="pi-part-number-pdf-") as tmp:
        root = Path(tmp)
        for part_number in QA_PART_NUMBERS:
            diagnostics: list[str] = []
            started = time.perf_counter()
            result = search_product_pdfs_by_part_number(
                part_number,
                root / part_number,
                limit=8,
                timeout=10,
                log=diagnostics.append,
            )
            elapsed = time.perf_counter() - started
            candidates = [_candidate_payload(row) for row in result.candidates]
            resolved = result.resolved.identity
            products.append(
                ProductBenchmark(
                    product=part_number,
                    elapsed_seconds=round(elapsed, 3),
                    resolved_brand=resolved.brand,
                    resolved_model=resolved.model or resolved.product_name,
                    official_domain=result.resolved.official_domain,
                    identity_status=result.resolved.status,
                    identity_diagnostics=dict(result.resolved.diagnostics or {}),
                    discovered=result.discovered_count,
                    downloaded=result.downloaded_count,
                    validated=result.validated_count,
                    rejected=result.rejected_count,
                    duplicates=result.duplicate_count,
                    page_limit_rejected=result.page_limit_rejected_count,
                    candidates=candidates,
                    diagnostic_log=diagnostics[-60:],
                    gate_failures=_failures(part_number, result, candidates),
                )
            )

    report = {
        "status": "PASS" if all(not row.gate_failures for row in products) else "FAIL",
        "input_mode": "part_number_only_real_api",
        "contract": {
            "products_required": len(QA_PART_NUMBERS),
            "all_products_require_official_domain": True,
            "all_products_require_discovered_pdf": True,
            "all_products_require_download_attempt": True,
            "all_products_require_validated_pdf": True,
            "cross_product_contamination_allowed": False,
            "surface_only_pdf": True,
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
    print("PART_NUMBER_PDF_SEARCH_BENCHMARK=" + json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(1)
    return report


if __name__ == "__main__":
    run()
