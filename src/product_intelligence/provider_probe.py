from __future__ import annotations

import io
from dataclasses import dataclass

import requests
from PIL import Image, ImageDraw

from .key_store import load_value
from .mistral_client import MistralClient
from .ocr_space_client import OCRSpaceClient


@dataclass(frozen=True)
class ProbeResult:
    provider: str
    status: str
    detail: str = ""


def _safe_failure(provider: str, status: str, exc: Exception | None = None, *, detail: str = "") -> ProbeResult:
    # Never expose raw exception text: HTTP/client exceptions may echo credentials or headers.
    safe_detail = str(detail or "").strip() or (type(exc).__name__ if exc is not None else "")
    return ProbeResult(provider=provider, status=status, detail=safe_detail)


def _network_detail(exc: Exception) -> str:
    # Order matters because ProxyError/SSLError are ConnectionError subclasses.
    if isinstance(exc, requests.exceptions.ProxyError):
        return "PROXY"
    if isinstance(exc, requests.exceptions.SSLError):
        return "SSL_TLS"
    if isinstance(exc, requests.Timeout):
        return "TIMEOUT"
    if isinstance(exc, requests.ConnectionError):
        return "CONNECTION"
    return "NETWORK"


def _retryable_network_error(exc: Exception) -> bool:
    # Retry only failures that are commonly transient. A broken proxy/TLS chain should
    # be reported immediately instead of repeating the same expensive request.
    if isinstance(exc, (requests.exceptions.ProxyError, requests.exceptions.SSLError)):
        return False
    return isinstance(exc, (requests.Timeout, requests.ConnectionError))


def _probe_png() -> bytes:
    image = Image.new("RGB", (360, 96), "white")
    draw = ImageDraw.Draw(image)
    draw.text((18, 34), "STECH OCR TEST", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def probe_ocr_space(*, timeout: int = 20, client=None) -> ProbeResult:
    provider = "OCR.space"
    if not (load_value("ocr_space_api_key") or "").strip():
        return ProbeResult(provider, "SIN CONFIGURAR", "")
    active = client or OCRSpaceClient(lambda: load_value("ocr_space_api_key"))
    image = _probe_png()
    for attempt in range(2):
        try:
            text = active.extract(image, language="eng", timeout=int(timeout))
            break
        except requests.HTTPError as exc:
            return _safe_failure(provider, "RECHAZADO", exc, detail="HTTP_REJECTED")
        except requests.RequestException as exc:
            if attempt == 0 and _retryable_network_error(exc):
                continue
            return _safe_failure(provider, "ERROR DE RED", exc, detail=_network_detail(exc))
        except Exception as exc:
            return _safe_failure(provider, "RECHAZADO", exc)
    else:  # pragma: no cover - loop always returns/breaks
        return ProbeResult(provider, "ERROR DE RED", "NETWORK")
    if not str(text or "").strip():
        return ProbeResult(provider, "RECHAZADO", "EMPTY_PROVIDER_RESPONSE")
    return ProbeResult(provider, "CONECTADO", "OCR_RESPONSE_OK")


def probe_mistral(*, model: str = "mistral-small-latest", timeout: int = 20, client=None) -> ProbeResult:
    provider = "Mistral"
    if not (load_value("mistral_api_key") or "").strip():
        return ProbeResult(provider, "SIN CONFIGURAR", "")
    active = client or MistralClient(lambda: load_value("mistral_api_key"))
    payload = {
        "task": "connection_probe",
        "instructions": "Responde únicamente STECH_OK.",
    }
    try:
        text = active.generate(payload, model=model or "mistral-small-latest", timeout=int(timeout))
    except requests.HTTPError as exc:
        return _safe_failure(provider, "RECHAZADO", exc, detail="HTTP_REJECTED")
    except requests.RequestException as exc:
        return _safe_failure(provider, "ERROR DE RED", exc, detail=_network_detail(exc))
    except Exception as exc:
        return _safe_failure(provider, "RECHAZADO", exc)
    if not str(text or "").strip():
        return ProbeResult(provider, "RECHAZADO", "EMPTY_PROVIDER_RESPONSE")
    return ProbeResult(provider, "CONECTADO", "MISTRAL_RESPONSE_OK")
