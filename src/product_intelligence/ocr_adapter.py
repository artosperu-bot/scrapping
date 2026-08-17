from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .capabilities import is_available
from .local_ocr import rapidocr_text


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float
    page: int | None = None
    bbox: Any = None


class OCRUnavailable(RuntimeError):
    pass


class OCRProvider(Protocol):
    """Remote/local OCR contract used by PDF extraction and tests."""

    def extract(self, image_bytes: bytes, *, language: str, timeout: int) -> str:
        ...


def extract_with_provider(
    image_bytes: bytes,
    provider: OCRProvider | None,
    *,
    language: str = "en",
    timeout: int = 20,
) -> str:
    if provider is None:
        return ""
    try:
        return str(provider.extract(image_bytes, language=language, timeout=int(timeout)) or "").strip()
    except Exception:
        return ""


def available() -> bool:
    return is_available("ocr")


def extract_text(image_path: str | Path, *, lang: str = "en") -> list[OCRLine]:
    """Compatibility adapter backed by the cached RapidOCR CPU engine.

    The actual reviewed-PDF path calls ``rapidocr_text`` directly on rendered page
    bytes. This function remains for legacy callers that supply an image path.
    Product/document identity must already be validated before invoking OCR.
    """
    if not available():
        raise OCRUnavailable(
            "OCR local no está instalado. Instala el perfil opcional con: pip install -e '.[ocr]'"
        )
    try:
        data = Path(image_path).read_bytes()
    except OSError:
        return []
    text = rapidocr_text(data)
    return [OCRLine(text=line.strip(), confidence=0.80) for line in text.splitlines() if line.strip()]


def joined_text(lines: list[OCRLine], *, min_confidence: float = 0.65) -> str:
    return "\n".join(line.text for line in lines if line.confidence >= min_confidence)
