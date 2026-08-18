from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import fitz

from .models import ProductIdentity
from .pdf_extract import extract_pdf_bytes
from .product_document_matcher import (
    DocumentFingerprint,
    ProductDocumentMatch,
    ProductDocumentMatcher,
    ProductFingerprint,
)


@dataclass(frozen=True)
class VerifiedPdfExtraction:
    accepted: bool
    match: ProductDocumentMatch
    text: str = ""
    evidence: tuple[Any, ...] = ()


def native_pdf_identity_text(data: bytes, *, max_pages: int = 10) -> str:
    """Read a bounded amount of native PDF text for identity only.

    This function intentionally performs no OCR. It exists so that a sibling,
    related-family or unknown document is rejected before OCR/Mistral/full
    extraction can spend resources or create contaminating evidence.
    """
    if not bytes(data or b"").startswith(b"%PDF-"):
        raise ValueError("Los bytes no corresponden a un PDF válido")
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        parts: list[str] = []
        metadata = doc.metadata or {}
        for key in ("title", "subject", "keywords", "author"):
            value = str(metadata.get(key) or "").strip()
            if value:
                parts.append(value)
        limit = min(len(doc), max(1, int(max_pages)))
        for index in range(limit):
            text = (doc[index].get_text("text") or "").strip()
            if text:
                parts.append(text)
        return "\n".join(parts)
    finally:
        doc.close()


def extract_verified_pdf_bytes(
    identity: ProductIdentity,
    data: bytes,
    source_url: str,
    *,
    full_extract: Callable[..., tuple[str, list[Any] | tuple[Any, ...]]] = extract_pdf_bytes,
    match_level: str = "HIGH",
    confidence: float = .90,
    parent_source_url: str | None = None,
    focus_terms=None,
) -> VerifiedPdfExtraction:
    """Validate exact product relationship before allowing full PDF extraction.

    Native text + metadata are used for the preflight because reading them does
    not invoke OCR. Only EXACT_SKU / EXACT_MODEL matches reach ``full_extract``.
    """
    preflight_text = native_pdf_identity_text(data)
    product = ProductFingerprint.from_identity(identity)
    document = DocumentFingerprint.from_evidence(
        url=source_url,
        text=preflight_text,
        source_page=parent_source_url,
    )
    match = ProductDocumentMatcher().match(product, document)
    if not match.accepted:
        return VerifiedPdfExtraction(False, match, "", ())

    text, evidence = full_extract(
        data,
        source_url,
        match_level=match_level,
        confidence=confidence,
        focus_terms=focus_terms,
        parent_source_url=parent_source_url,
    )
    return VerifiedPdfExtraction(True, match, text, tuple(evidence or ()))
