from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import fitz
import requests

from .models import Evidence
from .provider_runtime import remote_ocr_text
from .web_fetch import UA


@dataclass(frozen=True)
class ExtractedPdfPage:
    page: int
    text: str
    method: str


def download_bytes(url: str, timeout: int = 35) -> bytes:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": UA, "Accept": "application/pdf,*/*;q=0.8"})
    r.raise_for_status()
    if not ("application/pdf" in (r.headers.get("Content-Type") or "").lower() or r.content[:5] == b"%PDF-"):
        raise ValueError("La URL no devolvió un PDF válido")
    return r.content


def _local_ocr_page(image_bytes: bytes) -> str:
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        result = ocr.ocr(image_bytes, cls=True)
        lines = []
        for group in result or []:
            for item in group or []:
                if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], (list, tuple)):
                    lines.append(str(item[1][0]))
        return "\n".join(lines)
    except Exception:
        return ""


def _default_ocr_page(page_number: int, image_bytes: bytes) -> str:
    """Try configured OCR.space first, then preserve the existing local fallback."""
    remote = remote_ocr_text(image_bytes, language="eng")
    if remote:
        return remote
    return _local_ocr_page(image_bytes)


def _extract_document(doc: fitz.Document, ocr_page: Callable[[int, bytes], str] | None = None) -> list[ExtractedPdfPage]:
    pages = []
    for index, page in enumerate(doc):
        text = (page.get_text("text") or "").strip()
        method = "TEXT"
        if len(text) < 8:
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


def extract_pdf_pages(path: str | Path, ocr_page: Callable[[int, bytes], str] | None = None) -> list[ExtractedPdfPage]:
    doc = fitz.open(str(path))
    try:
        return _extract_document(doc, ocr_page=ocr_page)
    finally:
        doc.close()


def _evidence_from_pages(pages: list[ExtractedPdfPage], source_url: str, match_level: str, confidence: float) -> list[Evidence]:
    evidence = []
    for page in pages:
        for line in page.text.splitlines():
            m = re.match(r"^\s*([^:]{2,120})\s*:\s*(.{1,300})\s*$", line)
            if not m:
                continue
            evidence.append(Evidence(
                attribute=m.group(1).strip(), raw_value=m.group(2).strip(), normalized_value=m.group(2).strip(),
                source_url=source_url, source_type="official_pdf", page=page.page,
                selector=f"method={page.method}", match_level=match_level, confidence=confidence,
            ))
    return evidence


def extract_pdf_bytes(data: bytes, source_url: str, match_level: str = "HIGH", confidence: float = .90) -> tuple[str, list[Evidence]]:
    if not bytes(data or b"").startswith(b"%PDF-"):
        raise ValueError("Los bytes no corresponden a un PDF válido")
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        pages = _extract_document(doc)
    finally:
        doc.close()
    return "\n".join(page.text for page in pages), _evidence_from_pages(pages, source_url, match_level, confidence)


def extract_pdf(url: str, match_level: str = "HIGH", confidence: float = .90) -> tuple[str, list[Evidence]]:
    return extract_pdf_bytes(download_bytes(url), url, match_level, confidence)


def optional_docling_extract(path: str) -> str | None:
    try:
        from docling.document_converter import DocumentConverter
        result = DocumentConverter().convert(path)
        return result.document.export_to_markdown()
    except Exception:
        return None
