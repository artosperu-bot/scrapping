from __future__ import annotations

from pathlib import Path


def desktop_asset_path(filename: str, *, frozen_root: Path | None = None) -> Path:
    if frozen_root is not None:
        return Path(frozen_root) / "product_intelligence" / "assets" / filename
    return Path(__file__).resolve().parent / "assets" / filename
