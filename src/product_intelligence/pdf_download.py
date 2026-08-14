from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

from .web_fetch import UA


@dataclass(frozen=True)
class DownloadedPdf:
    path: Path
    source_url: str
    final_url: str
    content_type: str
    size_bytes: int
    sha256: str


def _safe_filename(url: str, digest: str) -> str:
    name = Path(urlparse(url).path).name or f"document-{digest[:12]}.pdf"
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name


def download_pdf(url: str, destination_dir: Path, *, timeout: int = 20, trace=None) -> DownloadedPdf:
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": UA, "Accept": "application/pdf,*/*;q=0.5"},
            allow_redirects=True,
        )
        response.raise_for_status()
        content = bytes(response.content or b"")
        ctype = str(response.headers.get("content-type") or "").lower()
        final_url = str(getattr(response, "url", url) or url)
        is_pdf = "application/pdf" in ctype or content.startswith(b"%PDF-")
        if not is_pdf:
            if trace:
                trace.emit("PDF_DOWNLOAD_REJECTED", url=url, reason="NOT_PDF")
            raise ValueError("NOT_PDF")
        digest = hashlib.sha256(content).hexdigest()
        target = destination_dir / _safe_filename(final_url, digest)
        fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(destination_dir))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        if trace:
            trace.emit("PDF_DOWNLOAD_OK", url=final_url, bytes=len(content), sha256=digest)
        return DownloadedPdf(
            path=target,
            source_url=url,
            final_url=final_url,
            content_type=ctype,
            size_bytes=len(content),
            sha256=digest,
        )
    except requests.RequestException as exc:
        if trace:
            trace.emit("PDF_DOWNLOAD_REJECTED", url=url, reason=type(exc).__name__)
        raise
