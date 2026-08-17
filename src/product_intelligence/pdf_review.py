from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Callable
from urllib.parse import urlparse

import fitz

from .document_discovery import (
    DocumentProvenance,
    assess_document_candidate,
    can_bind_document_by_provenance,
    classify_document_candidate,
    discover_product_documents,
)
from .models import ProductIdentity
from .pdf_download import download_pdf
from .pdf_evidence import validate_pdf_identity


_PROVENANCE_LOCK = RLock()
_DISCOVERED_PROVENANCE: dict[str, DocumentProvenance] = {}
MAX_REVIEW_PDF_PAGES = 10


def provenance_for_review_url(url: str) -> DocumentProvenance | None:
    with _PROVENANCE_LOCK:
        return _DISCOVERED_PROVENANCE.get(str(url or "").strip())


def _remember_provenance(url: str, provenance: DocumentProvenance | None) -> None:
    if provenance is None:
        return
    with _PROVENANCE_LOCK:
        _DISCOVERED_PROVENANCE[str(url or "").strip()] = provenance


@dataclass(frozen=True)
class PdfReviewCandidate:
    url: str
    title: str = ""
    snippet: str = ""
    document_type: str = "technical_pdf"
    likely_official: bool = False
    discovery_score: float = 0.0
    review_score: int = 0
    provenance: DocumentProvenance | None = None
    identity_status: str = "UNVERIFIED"
    identity_reason: str = ""
    identity_score: int = 0

    @property
    def host(self) -> str:
        return (urlparse(self.url).hostname or "").lower().removeprefix("www.")

    @property
    def authority_label(self) -> str:
        if self.provenance and self.provenance.parent_authority:
            return self.provenance.parent_authority
        return "OFFICIAL" if self.likely_official else "SOURCE"


@dataclass(frozen=True)
class PdfInspection:
    url: str
    final_url: str
    local_path: Path
    identity_accepted: bool
    identity_pending_ocr: bool
    identity_provenance_bound: bool
    identity_confidence: float
    identity_reason: str
    page_count: int
    native_text_chars: int
    ocr_recommended: bool
    preview_png: bytes
    review_score: int
    selection_allowed: bool
    provenance: DocumentProvenance | None = None


def _document_priority(document_type: str) -> int:
    return {
        "manual": 20,
        "datasheet": 20,
        "quick_start": 14,
        "compliance": 9,
        "technical_pdf": 12,
    }.get(str(document_type or "technical_pdf"), 8)


def score_review_candidate(
    *,
    likely_official: bool,
    document_type: str,
    discovery_score: float,
    identity_accepted: bool | None = None,
    identity_confidence: float = 0.0,
    native_text_chars: int | None = None,
    provenance: DocumentProvenance | None = None,
    identity_score: int = 0,
) -> int:
    """Transparent review score only; never an evidence admission gate."""
    score = round(max(0, min(100, int(identity_score or 0))) * 0.40)
    score += 20 if likely_official else 8
    score += 15 if provenance is not None else 0
    score += round(_document_priority(document_type) / 20 * 10)
    score += round(max(0.0, min(1.0, float(discovery_score or 0.0))) * 5)
    if identity_accepted is True:
        score = max(
            score,
            round(max(0.0, min(1.0, float(identity_confidence or 0.0))) * 40)
            + (20 if likely_official else 8)
            + (15 if provenance else 0)
            + round(_document_priority(document_type) / 20 * 10),
        )
    elif identity_accepted is False:
        score -= 25
    if native_text_chars is not None:
        chars = max(0, int(native_text_chars or 0))
        score += 10 if chars >= 1000 else 6 if chars >= 200 else 2 if chars >= 40 else 0
    return max(0, min(100, int(score)))


def discover_review_candidates(identity: ProductIdentity, limit: int = 8) -> list[PdfReviewCandidate]:
    """Discover metadata candidates only. No PDF is downloaded in this phase."""
    rows = discover_product_documents(identity, limit=max(1, int(limit)))
    out: list[PdfReviewCandidate] = []
    seen: set[str] = set()
    for row in rows:
        url = str(row.url or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        kind = classify_document_candidate(row.url, row.title, row.snippet) or "technical_pdf"
        provenance = getattr(row, "provenance", None)

        # Resolved landing children carry structured identity fields. A third-party
        # landing may match the product exactly, but that identity is not
        # transferable to a generic child PDF. Without trusted manufacturer
        # provenance the child must prove identity from its own URL/title.
        structured_identity = hasattr(row, "identity_status")
        if provenance is None and structured_identity:
            own_identity = assess_document_candidate(identity, row.url, row.title, "")
            if not own_identity.accepted:
                continue
            identity_status = "EXACT" if own_identity.exact_strong_id or own_identity.exact_model else "STRONG"
            identity_reason = own_identity.reason
            identity_score = own_identity.identity_score
        else:
            identity_status = str(getattr(row, "identity_status", "UNVERIFIED") or "UNVERIFIED")
            identity_reason = str(getattr(row, "identity_reason", "") or "")
            identity_score = int(getattr(row, "identity_score", 0) or 0)

        _remember_provenance(url, provenance)
        out.append(
            PdfReviewCandidate(
                url=url,
                title=str(row.title or ""),
                snippet=str(row.snippet or ""),
                document_type=kind,
                likely_official=bool(getattr(row, "likely_official", False)),
                discovery_score=float(getattr(row, "score", 0.0) or 0.0),
                provenance=provenance,
                identity_status=identity_status,
                identity_reason=identity_reason,
                identity_score=identity_score,
                review_score=score_review_candidate(
                    likely_official=bool(getattr(row, "likely_official", False)),
                    document_type=kind,
                    discovery_score=float(getattr(row, "score", 0.0) or 0.0),
                    provenance=provenance,
                    identity_score=identity_score,
                ),
            )
        )
    out.sort(key=lambda item: item.review_score, reverse=True)
    return out[: max(1, int(limit))]


def _native_text(doc: fitz.Document) -> tuple[str, int]:
    parts: list[str] = []
    for page in doc:
        text = str(page.get_text("text") or "").strip()
        if text:
            parts.append(text)
    joined = "\n".join(parts)
    return joined, len(joined)


def _ocr_recommended(page_count: int, native_text_chars: int) -> bool:
    pages = max(1, int(page_count or 0))
    chars = max(0, int(native_text_chars or 0))
    if chars < 40:
        return True
    return (chars / pages) < 35


def _identity_pending_ocr(*, accepted: bool, reason: str, ocr_recommended: bool, provenance_bound: bool = False) -> bool:
    if accepted or provenance_bound or not ocr_recommended:
        return False
    return str(reason or "") in {
        "strong_identifier_missing",
        "strong_identifier_without_brand_binding",
        "identity_not_confirmed",
    }


def render_pdf_page(local_path: str | Path, page_index: int, zoom: float = 1.35) -> bytes:
    """Render one page on demand. The caller owns caching policy."""
    path = Path(local_path)
    doc = fitz.open(path)
    try:
        if doc.page_count < 1:
            return b""
        index = max(0, min(int(page_index), int(doc.page_count) - 1))
        scale = max(0.5, min(3.0, float(zoom or 1.0)))
        page = doc.load_page(index)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def _preview_first_page(doc: fitz.Document) -> bytes:
    if doc.page_count < 1:
        return b""
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
    return pix.tobytes("png")


def inspect_pdf_candidate(
    identity: ProductIdentity,
    url: str,
    cache_dir: str | Path,
    *,
    document_type: str = "technical_pdf",
    likely_official: bool = False,
    discovery_score: float = 0.0,
    provenance: DocumentProvenance | None = None,
    identity_score: int = 0,
    on_stage: Callable[..., None] | None = None,
) -> PdfInspection:
    """Download a preview candidate and inspect it; optional callbacks expose stages only."""
    _remember_provenance(url, provenance)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    downloaded = download_pdf(url, cache, timeout=30)
    local_path = Path(downloaded.path)
    if on_stage:
        on_stage(
            "downloaded",
            local_path=local_path,
            final_url=str(downloaded.final_url or url),
        )
        on_stage(
            "validating",
            local_path=local_path,
            final_url=str(downloaded.final_url or url),
        )
    doc = fitz.open(local_path)
    try:
        native_text, native_chars = _native_text(doc)
        match = validate_pdf_identity(identity, native_text, str(downloaded.final_url or url))
        preview = _preview_first_page(doc)
        pages = int(doc.page_count)
    finally:
        doc.close()

    # Product policy requested for reviewed PDFs: documents above ten pages are
    # discarded before OCR/provider processing regardless of otherwise good ID.
    if pages > MAX_REVIEW_PDF_PAGES:
        return PdfInspection(
            url=url,
            final_url=str(downloaded.final_url or url),
            local_path=local_path,
            identity_accepted=False,
            identity_pending_ocr=False,
            identity_provenance_bound=False,
            identity_confidence=0.0,
            identity_reason="page_limit_exceeded",
            page_count=pages,
            native_text_chars=native_chars,
            ocr_recommended=False,
            preview_png=preview,
            review_score=0,
            selection_allowed=False,
            provenance=provenance,
        )

    provenance_bound = (not bool(match.accepted)) and can_bind_document_by_provenance(
        provenance,
        internal_identity_reason=str(match.reason),
    )
    accepted = bool(match.accepted) or provenance_bound
    confidence = float(match.confidence)
    reason = str(match.reason)
    if provenance_bound:
        confidence = max(
            confidence,
            min(0.96, float(provenance.parent_identity_confidence if provenance else 0.0) * 0.95),
        )
        reason = "identity_bound_by_provenance"

    ocr_recommended = _ocr_recommended(pages, native_chars)
    pending_ocr = _identity_pending_ocr(
        accepted=accepted,
        reason=str(match.reason),
        ocr_recommended=ocr_recommended,
        provenance_bound=provenance_bound,
    )
    selection_allowed = bool(accepted or pending_ocr)
    score = score_review_candidate(
        likely_official=likely_official,
        document_type=document_type,
        discovery_score=discovery_score,
        identity_accepted=None if pending_ocr else accepted,
        identity_confidence=confidence,
        native_text_chars=native_chars,
        provenance=provenance,
        identity_score=identity_score,
    )
    return PdfInspection(
        url=url,
        final_url=str(downloaded.final_url or url),
        local_path=local_path,
        identity_accepted=accepted,
        identity_pending_ocr=pending_ocr,
        identity_provenance_bound=provenance_bound,
        identity_confidence=confidence,
        identity_reason=reason,
        page_count=pages,
        native_text_chars=native_chars,
        ocr_recommended=ocr_recommended,
        preview_png=preview,
        review_score=score,
        selection_allowed=selection_allowed,
        provenance=provenance,
    )
