from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import ProductIdentity
from .live_pdf_discovery import discover_validated_review_pdfs_live as discover_validated_review_pdfs
from .pdf_pipeline import ResolvedPdfIdentity, ValidatedPdfCandidate


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


def _clean(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _primary_identifier(identity: ProductIdentity) -> str:
    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or "").strip()


def search_product_pdfs(
    cache_dir: str | Path,
    *,
    mpn: str | None = None,
    ean: str | None = None,
    upc: str | None = None,
    gtin: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    product_name: str | None = None,
    limit: int = 8,
    timeout: int = 10,
    log: Callable[[str], None] | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> PartNumberPdfSearchResult:
    """Resolve identity and surface validated short PDFs, with optional live events."""
    mpn = _clean(mpn)
    ean = _clean(ean)
    upc = _clean(upc)
    gtin = _clean(gtin)
    brand = _clean(brand)
    model = _clean(model)
    product_name = _clean(product_name)
    primary = mpn or ean or upc or gtin
    if not primary:
        raise ValueError("product_identifier_required")

    identity = ProductIdentity(
        brand=brand,
        product_name=product_name,
        model=model or product_name or primary,
        mpn=mpn,
        ean=ean,
        upc=upc,
        gtin=gtin,
    )

    accepted_live_urls: set[str] = set()
    page_limit_live_urls: set[str] = set()

    def forward(event: dict):
        kind = str(event.get("type") or "")
        if kind == "done":
            return
        if kind == "validated" and event.get("row") is not None:
            row = event["row"]
            pages = int(getattr(row.inspection, "page_count", 0) or 0)
            url = str(getattr(row.candidate, "url", "") or "")
            if pages > MAX_REVIEW_PDF_PAGES:
                page_limit_live_urls.add(url)
                if on_event:
                    on_event(
                        {
                            "type": "rejected",
                            "stage": "VALIDATE",
                            "url": url,
                            "reason": "PAGE_LIMIT",
                            "pages": pages,
                            "max_pages": MAX_REVIEW_PDF_PAGES,
                        }
                    )
                return
            accepted_live_urls.add(url)
        if on_event:
            on_event(event)

    result = discover_validated_review_pdfs(
        identity,
        cache_dir,
        limit=max(1, int(limit)),
        timeout=max(1, int(timeout)),
        log=log,
        on_event=forward,
    )

    accepted: list[ValidatedPdfCandidate] = []
    page_limit_rejected = 0
    for row in result.candidates:
        pages = int(getattr(row.inspection, "page_count", 0) or 0)
        if pages > MAX_REVIEW_PDF_PAGES:
            page_limit_rejected += 1
            if log:
                log(f"[PAGE_LIMIT] REJECTED {row.candidate.url} · pages={pages} max={MAX_REVIEW_PDF_PAGES}")
            # A mocked/legacy producer may not have emitted the validated event.
            url = str(row.candidate.url or "")
            if url not in page_limit_live_urls and on_event:
                on_event(
                    {
                        "type": "rejected",
                        "stage": "VALIDATE",
                        "url": url,
                        "reason": "PAGE_LIMIT",
                        "pages": pages,
                        "max_pages": MAX_REVIEW_PDF_PAGES,
                    }
                )
            continue
        accepted.append(row)
        # Compatibility with producers that return rows without live candidate callbacks.
        url = str(row.candidate.url or "")
        if url not in accepted_live_urls and on_event:
            on_event({"type": "validated", "stage": "VALIDATE", "row": row, "url": url, "pages": pages})

    if log:
        resolved = result.resolved.identity
        log(
            f"[PRODUCT_PDF_RESULT] identifier={primary} brand={resolved.brand or '-'} "
            f"model={resolved.model or resolved.product_name or '-'} "
            f"validated={len(accepted)} page_limit_rejected={page_limit_rejected}"
        )

    final = PartNumberPdfSearchResult(
        part_number=primary,
        resolved=result.resolved,
        candidates=tuple(accepted),
        discovered_count=result.discovered_count,
        downloaded_count=result.downloaded_count,
        validated_count=len(accepted),
        rejected_count=result.rejected_count + page_limit_rejected,
        duplicate_count=result.duplicate_count,
        page_limit_rejected_count=page_limit_rejected,
    )
    if on_event:
        on_event(
            {
                "type": "done",
                "stage": "DONE",
                "discovered": final.discovered_count,
                "downloaded": final.downloaded_count,
                "validated": final.validated_count,
                "rejected": final.rejected_count,
                "duplicates": final.duplicate_count,
                "page_limit_rejected": final.page_limit_rejected_count,
            }
        )
    return final


def search_product_pdfs_by_part_number(
    part_number: str,
    cache_dir: str | Path,
    *,
    limit: int = 8,
    timeout: int = 10,
    log: Callable[[str], None] | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> PartNumberPdfSearchResult:
    part = _clean(part_number)
    if not part:
        raise ValueError("part_number_required")
    return search_product_pdfs(
        cache_dir,
        mpn=part,
        model=part,
        limit=limit,
        timeout=timeout,
        log=log,
        on_event=on_event,
    )
