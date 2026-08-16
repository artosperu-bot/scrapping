from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import ProductIdentity
from .pdf_pipeline import ResolvedPdfIdentity, ValidatedPdfCandidate, discover_validated_review_pdfs


MAX_REVIEW_PDF_PAGES = 10


@dataclass(frozen=True)
class PartNumberPdfSearchResult:
    part_number: str
    resolved: ResolvedPdfIdentity
    candidates: tuple[ValidatedPdfCandidate, ...]
    discovered_count: int
    downloaded_count: int
    validated_count: int
    rejected_count: int
    duplicate_count: int
    page_limit_rejected_count: int


def _clean_part_number(value: str) -> str:
    return str(value or "").strip()


def search_product_pdfs_by_part_number(
    part_number: str,
    cache_dir: str | Path,
    *,
    limit: int = 8,
    timeout: int = 10,
    log: Callable[[str], None] | None = None,
) -> PartNumberPdfSearchResult:
    """Find only validated PDFs for one product starting from a raw Part Number.

    Contract:
    - input is the Part Number only;
    - web/HTML may be used only to resolve identity and discover document links;
    - output contains PDFs only, already downloaded and identity-validated;
    - OCR, Mistral and specification extraction are not invoked here;
    - PDFs longer than MAX_REVIEW_PDF_PAGES are not surfaced.
    """
    part = _clean_part_number(part_number)
    if not part:
        raise ValueError("part_number_required")

    identity = ProductIdentity(model=part, mpn=part)
    result = discover_validated_review_pdfs(
        identity,
        cache_dir,
        limit=max(1, int(limit)),
        timeout=max(1, int(timeout)),
        log=log,
    )

    accepted: list[ValidatedPdfCandidate] = []
    page_limit_rejected = 0
    for row in result.candidates:
        pages = int(getattr(row.inspection, "page_count", 0) or 0)
        if pages > MAX_REVIEW_PDF_PAGES:
            page_limit_rejected += 1
            if log:
                log(
                    f"[PAGE_LIMIT] REJECTED {row.candidate.url} · pages={pages} "
                    f"max={MAX_REVIEW_PDF_PAGES}"
                )
            continue
        accepted.append(row)

    if log:
        resolved = result.resolved.identity
        log(
            f"[PART_NUMBER_PDF_RESULT] part={part} brand={resolved.brand or '-'} "
            f"model={resolved.model or resolved.product_name or '-'} "
            f"validated={len(accepted)} page_limit_rejected={page_limit_rejected}"
        )

    return PartNumberPdfSearchResult(
        part_number=part,
        resolved=result.resolved,
        candidates=tuple(accepted),
        discovered_count=result.discovered_count,
        downloaded_count=result.downloaded_count,
        validated_count=len(accepted),
        rejected_count=result.rejected_count + page_limit_rejected,
        duplicate_count=result.duplicate_count,
        page_limit_rejected_count=page_limit_rejected,
    )
