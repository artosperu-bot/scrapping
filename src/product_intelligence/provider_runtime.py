from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable

from .key_store import load_value
from .mistral_client import MistralClient
from .ocr_adapter import extract_with_provider
from .ocr_space_client import OCRSpaceClient

_DEFAULTS = {
    "ocr_space_enabled": False,
    "mistral_enabled": False,
    "mistral_model": "mistral-small-latest",
    "request_timeout": 20,
}

_run_settings: ContextVar[dict[str, Any]] = ContextVar("provider_run_settings", default=dict(_DEFAULTS))
_audit: ContextVar[Callable[[str, dict[str, Any]], None] | None] = ContextVar("provider_audit", default=None)


def current_settings() -> dict[str, Any]:
    merged = dict(_DEFAULTS)
    merged.update(_run_settings.get() or {})
    return merged


def emit(event: str, **data: Any) -> None:
    callback = _audit.get()
    if callback:
        safe = {k: v for k, v in data.items() if k.lower() not in {"api_key", "authorization", "token", "secret", "headers"}}
        callback(event, safe)


@contextmanager
def provider_run_scope(settings: dict[str, Any] | None, audit: Callable[[str, dict[str, Any]], None] | None = None):
    safe = {k: (settings or {}).get(k, v) for k, v in _DEFAULTS.items()}
    token_settings = _run_settings.set(safe)
    token_audit = _audit.set(audit)
    try:
        yield
    finally:
        _audit.reset(token_audit)
        _run_settings.reset(token_settings)


def remote_ocr_text(image_bytes: bytes, *, language: str = "eng") -> str:
    settings = current_settings()
    if not settings["ocr_space_enabled"]:
        emit("OCR_PROVIDER_SKIPPED", provider="OCR.space", reason="DISABLED")
        return ""
    if not load_value("ocr_space_api_key"):
        emit("OCR_PROVIDER_UNAVAILABLE", provider="OCR.space", reason="NO_CREDENTIAL")
        return ""
    provider = OCRSpaceClient(lambda: load_value("ocr_space_api_key"))
    emit("OCR_PROVIDER_SELECTED", provider="OCR.space")
    text = extract_with_provider(
        image_bytes,
        provider,
        language=language,
        timeout=int(settings["request_timeout"]),
    )
    if not text:
        emit("OCR_PROVIDER_UNAVAILABLE", provider="OCR.space", reason="EMPTY_OR_ERROR")
    return text


def mistral_narrator_client():
    """Return the intentionally unconfigured transport seam for this phase."""
    return MistralClient()
