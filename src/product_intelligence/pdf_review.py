from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import fitz

from .document_discovery import classify_document_candidate, discover_product_documents
from .models import ProductIdentity
from .pdf_download import download_pdf
from .pdf_evidence import validate_pdf_identity


@dataclass(frozen=True)
class PdfReviewCandidate:
    url: str
    title: str = ""
    snippet: str = ""
    document_type: str = "technical_pdf"
    likely_official: bool = False
    discovery_score: float = 0.0
    review_score: int = 0

    @property
    def host(self) -> str:
        return (urlparse(self.url).hostname or "").lower().removeprefix("www.")


@dataclass(frozen=True)
class PdfInspection:
    url: str
    final_url: str
    local_path: Path
    identity_accepted: bool
    identity_confidence: float
    identity_reason: str
    page_count: int
    native_text_chars: int
    ocr_recommended: bool
    preview_png: bytes
    review_score: int


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
) -> int:
    """Transparent review score only; never an evidence admission gate."""
    score = 10
    score += 22 if likely_official else 0
    score += _document_priority(document_type)
    score += round(max(0.0, min(1.0, float(discovery_score or 0.0))) * 18)
    if identity_accepted is True:
        score += round(max(0.0, min(1.0, float(identity_confidence or 0.0))) * 24)
    elif identity_accepted is False:
        score -= 35
    if native_text_chars is not None:
        chars = max(0, int(native_text_chars))
        score += 6 if chars >= 1000 else 3 if chars >= 100 else 0
    return max(0, min(100, int(score)))


def discover_review_candidates(identity: ProductIdentity, limit: int = 8) -> list[PdfReviewCandidate]:
    rows = discover_product_documents(identity, limit=max(1, int(limit)))
    out: list[PdfReviewCandidate] = []
    for row in rows:
        kind = classify_document_candidate(row.url, row.title, row.snippet) or "technical_pdf"
        out.append(PdfReviewCandidate(
            url=row.url,
            title=str(row.title or ""),
            snippet=str(row.snippet or ""),
            document_type=kind,
            likely_official=bool(getattr(row, "likely_official", False)),
            discovery_score=float(getattr(row, "score", 0.0) or 0.0),
            review_score=score_review_candidate(
                likely_official=bool(getattr(row, "likely_official", False)),
                document_type=kind,
                discovery_score=float(getattr(row, "score", 0.0) or 0.0),
            ),
        ))
    out.sort(key=lambda item: item.review_score, reverse=True)
    return out


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


def _preview_first_page(doc: fitz.Document) -> bytes:
    if doc.page_count < 1:
        return b""
    page = doc.load_page(0)
    matrix = fitz.Matrix(1.35, 1.35)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    return pix.tobytes("png")


def inspect_pdf_candidate(
    identity: ProductIdentity,
    url: str,
    cache_dir: str | Path,
    *,
    document_type: str = "technical_pdf",
    likely_official: bool = False,
    discovery_score: float = 0.0,
) -> PdfInspection:
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    downloaded = download_pdf(url, cache, timeout=30)
    local_path = Path(downloaded.path)
    doc = fitz.open(local_path)
    try:
        native_text, native_chars = _native_text(doc)
        match = validate_pdf_identity(identity, native_text, str(downloaded.final_url or url))
        preview = _preview_first_page(doc)
        pages = int(doc.page_count)
    finally:
        doc.close()

    score = score_review_candidate(
        likely_official=likely_official,
        document_type=document_type,
        discovery_score=discovery_score,
        identity_accepted=bool(match.accepted),
        identity_confidence=float(match.confidence),
        native_text_chars=native_chars,
    )
    return PdfInspection(
        url=url,
        final_url=str(downloaded.final_url or url),
        local_path=local_path,
        identity_accepted=bool(match.accepted),
        identity_confidence=float(match.confidence),
        identity_reason=str(match.reason),
        page_count=pages,
        native_text_chars=native_chars,
        ocr_recommended=_ocr_recommended(pages, native_chars),
        preview_png=preview,
        review_score=score,
    )
