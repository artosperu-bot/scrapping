from __future__ import annotations

import threading
from typing import Any, Callable


_engine = None
_engine_lock = threading.Lock()


def _build_rapidocr_engine():
    from rapidocr import RapidOCR

    return RapidOCR()


def _get_engine(factory: Callable[[], Any] | None = None):
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            _engine = (factory or _build_rapidocr_engine)()
        return _engine


def _result_text(result: Any) -> str:
    txts = getattr(result, "txts", None)
    if txts is None and isinstance(result, (list, tuple)) and result:
        # Compatibility with older RapidOCR result shapes without binding the
        # production path to one historical version.
        candidate = result[0] if len(result) == 2 else result
        if isinstance(candidate, (list, tuple)):
            rows = []
            for item in candidate:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    value = item[1]
                    if isinstance(value, (list, tuple)) and value:
                        rows.append(str(value[0]))
                    elif isinstance(value, str):
                        rows.append(value)
            return "\n".join(row.strip() for row in rows if row and row.strip())
        return ""
    return "\n".join(str(text).strip() for text in (txts or ()) if str(text).strip())


def rapidocr_text(image_bytes: bytes, *, engine_factory: Callable[[], Any] | None = None) -> str:
    """Run the bundled CPU OCR engine lazily and reuse it across PDF pages.

    The function is fail-open by design: OCR is a fallback after native PDF text
    and OCR.space, never a reason to abort a document that may still contain
    usable native evidence.
    """
    if not image_bytes:
        return ""
    try:
        engine = _get_engine(engine_factory)
        return _result_text(engine(image_bytes)).strip()
    except Exception:
        return ""


def reset_local_ocr_for_tests() -> None:
    global _engine
    with _engine_lock:
        _engine = None
