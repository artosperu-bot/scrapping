from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import fitz
import requests

from .local_ocr import rapidocr_text
from .models import Evidence
from .provider_runtime import remote_ocr_text
from .web_fetch import UA


SHORT_PDF_PAGE_LIMIT = 10
LONG_PDF_HEAD_PAGES = 8
LONG_PDF_MAX_PAGES = 15
_TECHNICAL_PAGE_HINTS = (
    "technical specifications",
    "technical specification",
    "specifications",
    "specification",
    "technical data",
    "product specifications",
    "especificaciones tecnicas",
    "especificaciones técnicas",
    "ficha tecnica",
    "ficha técnica",
    "dimensions",
    "battery",
    "processor",
    "memory",
    "display",
    "connectivity",
)


@dataclass(frozen=True)
class ExtractedPdfPage:
    page: int
    text: str
    method: str


@dataclass(frozen=True)
class PdfPageTextQuality:
    native_ok: bool
    ocr_required: bool
    reason: str
    printable_ratio: float
    alphanumeric_ratio: float
    technical_signal: bool


def download_bytes(url: str, timeout: int = 35) -> bytes:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": UA, "Accept": "application/pdf,*/*;q=0.8"})
    r.raise_for_status()
    if not ("application/pdf" in (r.headers.get("Content-Type") or "").lower() or r.content[:5] == b"%PDF-"):
        raise ValueError("La URL no devolvió un PDF válido")
    return r.content


def _local_ocr_page(image_bytes: bytes) -> str:
    """Low-resource offline fallback, initialized lazily and cached across pages."""
    return rapidocr_text(image_bytes)


def _default_ocr_page(page_number: int, image_bytes: bytes) -> str:
    """Try configured OCR.space first, then the bundled offline RapidOCR fallback."""
    remote = remote_ocr_text(image_bytes, language="eng")
    if remote:
        return remote
    return _local_ocr_page(image_bytes)


def _search_text(value: str | None) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[^a-z0-9áéíóúüñ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def assess_pdf_page_text_quality(text: str | None) -> PdfPageTextQuality:
    """Decide whether native PDF text is useful enough to avoid OCR.

    Uses multiple cheap quality signals while preserving concise native specification
    lines that were valid in the legacy extractor. OCR is a fallback and never an
    identity override.
    """
    raw = str(text or "").strip()
    if not raw:
        return PdfPageTextQuality(False, True, "empty_native_text", 0.0, 0.0, False)
    total = max(1, len(raw))
    printable = sum(1 for ch in raw if ch.isprintable() and not ch.isspace())
    alnum = sum(1 for ch in raw if ch.isalnum())
    printable_ratio = printable / total
    alphanumeric_ratio = alnum / total
    normalized = _search_text(raw)
    technical_signal = any(_search_text(hint) in normalized for hint in _TECHNICAL_PAGE_HINTS)
    tokens = re.findall(r"[A-Za-z0-9]+", raw)
    unique_ratio = len(set(token.casefold() for token in tokens)) / max(1, len(tokens))
    garbage_runs = len(re.findall(r"[^A-Za-z0-9\s]{3,}", raw))
    structured_short = bool(
        len(raw) >= 8
        and alphanumeric_ratio >= 0.40
        and printable_ratio >= 0.55
        and (re.search(r"[:=]", raw) or re.search(r"\d", raw) or technical_signal)
    )

    if len(raw) < 8:
        return PdfPageTextQuality(False, True, "native_text_too_sparse", printable_ratio, alphanumeric_ratio, technical_signal)
    if printable_ratio < 0.55 or alphanumeric_ratio < 0.35:
        return PdfPageTextQuality(False, True, "native_text_low_signal", printable_ratio, alphanumeric_ratio, technical_signal)
    if garbage_runs >= 3 and unique_ratio < 0.35:
        return PdfPageTextQuality(False, True, "native_text_garbled", printable_ratio, alphanumeric_ratio, technical_signal)
    if len(raw) < 24 and not structured_short:
        return PdfPageTextQuality(False, True, "native_text_too_sparse", printable_ratio, alphanumeric_ratio, technical_signal)
    return PdfPageTextQuality(True, False, "native_text_usable", printable_ratio, alphanumeric_ratio, technical_signal)


def select_pdf_page_indexes(
    page_texts: list[str],
    focus_terms: Iterable[str] | None = None,
    *,
    short_limit: int = SHORT_PDF_PAGE_LIMIT,
    head_pages: int = LONG_PDF_HEAD_PAGES,
    max_pages: int = LONG_PDF_MAX_PAGES,
) -> list[int]:
    """Select pages worth fully processing from a PDF.

    Short documents preserve the historical full-document behavior. Long documents
    keep the beginning for title/index/context, then prioritize exact identity terms
    and technical-specification pages. The result is always bounded by ``max_pages``.
    """
    texts = list(page_texts or [])
    total = len(texts)
    if total <= max(0, int(short_limit)):
        return list(range(total))

    limit = max(1, int(max_pages))
    head_count = min(total, max(0, int(head_pages)), limit)
    selected = list(range(head_count))
    selected_set = set(selected)
    if len(selected) >= limit:
        return selected

    normalized_focus = tuple(dict.fromkeys(
        term for term in (_search_text(value) for value in (focus_terms or [])) if len(term) >= 3
    ))
    normalized_hints = tuple(_search_text(value) for value in _TECHNICAL_PAGE_HINTS)

    def signals(index: int) -> tuple[int, int]:
        hay = _search_text(texts[index])
        focus_hits = sum(1 for term in normalized_focus if term in hay)
        technical_hits = sum(1 for term in normalized_hints if term and term in hay)
        return focus_hits, technical_hits

    focus_candidates = []
    technical_candidates = []
    for index in range(head_count, total):
        focus_hits, technical_hits = signals(index)
        if focus_hits:
            focus_candidates.append((index, focus_hits, technical_hits))
        elif technical_hits:
            technical_candidates.append((index, technical_hits))

    focus_candidates.sort(key=lambda item: (-item[1], -item[2], item[0]))
    technical_candidates.sort(key=lambda item: (-item[1], item[0]))

    for index, _, _ in focus_candidates:
        if len(selected) >= limit:
            break
        if index not in selected_set:
            selected.append(index)
            selected_set.add(index)

    for index, _ in technical_candidates:
        if len(selected) >= limit:
            break
        if index not in selected_set:
            selected.append(index)
            selected_set.add(index)

    return selected


def _extract_selected_document(
    doc: fitz.Document,
    indexes: Iterable[int],
    *,
    native_texts: list[str] | None = None,
    ocr_page: Callable[[int, bytes], str] | None = None,
) -> list[ExtractedPdfPage]:
    pages = []
    for index in indexes:
        page = doc[index]
        text = (
            native_texts[index]
            if native_texts is not None and index < len(native_texts)
            else (page.get_text("text") or "")
        ).strip()
        method = "TEXT"
        quality = assess_pdf_page_text_quality(text)
        if quality.ocr_required:
            callback = ocr_page or _default_ocr_page
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                ocr_text = (callback(index + 1, pix.tobytes("png")) or "").strip()
            except Exception:
                ocr_text = ""
            if ocr_text:
                text = ocr_text
                method = "OCR"
        pages.append(ExtractedPdfPage(page=index + 1, text=text, method=method))
    return pages


def _extract_document(doc: fitz.Document, ocr_page: Callable[[int, bytes], str] | None = None) -> list[ExtractedPdfPage]:
    return _extract_selected_document(doc, range(len(doc)), ocr_page=ocr_page)


def extract_pdf_pages(path: str | Path, ocr_page: Callable[[int, bytes], str] | None = None) -> list[ExtractedPdfPage]:
    doc = fitz.open(str(path))
    try:
        return _extract_document(doc, ocr_page=ocr_page)
    finally:
        doc.close()


def _evidence_from_pages(
    pages: list[ExtractedPdfPage],
    source_url: str,
    match_level: str,
    confidence: float,
    *,
    parent_source_url: str | None = None,
) -> list[Evidence]:
    evidence = []
    for page in pages:
        for line in page.text.splitlines():
            m = re.match(r"^\s*([^:]{2,120})\s*:\s*(.{1,300})\s*$", line)
            if not m:
                continue
            raw_line = line.strip()[:500]
            evidence.append(Evidence(
                attribute=m.group(1).strip(), raw_value=m.group(2).strip(), normalized_value=m.group(2).strip(),
                source_url=source_url, source_type="official_pdf", parent_source_url=parent_source_url, page=page.page,
                selector=f"method={page.method}", extraction_method=page.method, raw_snippet=raw_line,
                match_level=match_level, confidence=confidence,
            ))
    return evidence


def extract_pdf_bytes(
    data: bytes,
    source_url: str,
    match_level: str = "HIGH",
    confidence: float = .90,
    *,
    focus_terms: Iterable[str] | None = None,
    parent_source_url: str | None = None,
) -> tuple[str, list[Evidence]]:
    if not bytes(data or b"").startswith(b"%PDF-"):
        raise ValueError("Los bytes no corresponden a un PDF válido")
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if len(doc) <= SHORT_PDF_PAGE_LIMIT:
            pages = _extract_document(doc)
        else:
            native_texts = [(page.get_text("text") or "").strip() for page in doc]
            selected_indexes = select_pdf_page_indexes(native_texts, focus_terms=focus_terms)
            pages = _extract_selected_document(doc, selected_indexes, native_texts=native_texts)
    finally:
        doc.close()
    return "\n".join(page.text for page in pages), _evidence_from_pages(
        pages,
        source_url,
        match_level,
        confidence,
        parent_source_url=parent_source_url,
    )


def extract_pdf(
    url: str,
    match_level: str = "HIGH",
    confidence: float = .90,
    *,
    focus_terms: Iterable[str] | None = None,
    parent_source_url: str | None = None,
) -> tuple[str, list[Evidence]]:
    return extract_pdf_bytes(
        download_bytes(url),
        url,
        match_level,
        confidence,
        focus_terms=focus_terms,
        parent_source_url=parent_source_url,
    )


def optional_docling_extract(path: str) -> str | None:
    try:
        from docling.document_converter import DocumentConverter
        result = DocumentConverter().convert(path)
        return result.document.export_to_markdown()
    except Exception:
        return None