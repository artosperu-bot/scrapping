from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .capabilities import is_available


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float
    page: int | None = None
    bbox: Any = None


class OCRUnavailable(RuntimeError):
    pass


class OCRProvider(Protocol):
    """Remote/local OCR contract used by PDF extraction and tests.

    Implementations receive bytes and return plain text only. Provider-specific
    credentials, HTTP details and secrets stay behind the implementation.
    """

    def extract(self, image_bytes: bytes, *, language: str, timeout: int) -> str:
        ...


def extract_with_provider(
    image_bytes: bytes,
    provider: OCRProvider | None,
    *,
    language: str = "en",
    timeout: int = 20,
) -> str:
    """Invoke a configured provider and fail closed on provider errors."""
    if provider is None:
        return ""
    try:
        return str(provider.extract(image_bytes, language=language, timeout=int(timeout)) or "").strip()
    except Exception:
        return ""


def available() -> bool:
    return is_available("ocr")


def extract_text(image_path: str | Path, *, lang: str = "en") -> list[OCRLine]:
    """Existing local OCR last-resort adapter.

    The caller must validate product/document identity before invoking OCR.
    OCR output is evidence with lower trust; it is never allowed to overwrite
    stronger structured HTML/PDF/API evidence by itself.
    """
    if not available():
        raise OCRUnavailable(
            "OCR no está instalado. Instala el perfil opcional con: pip install -e '.[ocr]'"
        )

    from paddleocr import PaddleOCR  # lazy optional import

    engine = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
    raw = engine.ocr(str(image_path), cls=True)
    lines: list[OCRLine] = []

    for page in raw or []:
        if not isinstance(page, (list, tuple)):
            continue
        for item in page:
            try:
                bbox = item[0]
                payload = item[1]
                text = str(payload[0]).strip()
                confidence = float(payload[1])
            except (TypeError, ValueError, IndexError):
                continue
            if text:
                lines.append(OCRLine(text=text, confidence=confidence, bbox=bbox))
    return lines


def joined_text(lines: list[OCRLine], *, min_confidence: float = 0.65) -> str:
    return "\n".join(line.text for line in lines if line.confidence >= min_confidence)
