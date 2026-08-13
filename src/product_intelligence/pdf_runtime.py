from __future__ import annotations

from pathlib import Path


def persist_pdf_bytes(output_root: str | None, data: bytes, filename: str = "document.pdf") -> str | None:
    if not output_root:
        return None
    folder = Path(output_root) / "pdf_evidence"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / filename
    dest.write_bytes(data)
    return str(dest)
