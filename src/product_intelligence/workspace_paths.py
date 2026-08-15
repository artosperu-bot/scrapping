from __future__ import annotations

import os
import re
import shutil
from pathlib import Path


_INVALID_WINDOWS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_RESERVED_WINDOWS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_RESULT_DIRS = ("Scraping", "PDF", "multimedia", "prices", "Logs")
_ALL_DIRS = ("Excel", *_RESULT_DIRS)


def default_jobs_root() -> Path:
    """Return a user-owned jobs root that is independent from the app install directory."""
    if os.name == "nt":
        documents = Path(os.environ.get("USERPROFILE") or Path.home()) / "Documents"
    else:
        documents = Path.home() / "Documents"
    return documents / "ProductIntelligence" / "Trabajos"


def sanitize_workspace_name(name: str) -> str:
    value = _INVALID_WINDOWS.sub("_", str(name or "").strip()).strip(" ._")
    value = re.sub(r"\s+", " ", value)
    if not value:
        value = "Trabajo"
    if value.upper() in _RESERVED_WINDOWS:
        value = f"{value}_Trabajo"
    return value[:96].rstrip(" .") or "Trabajo"


def workspace_dir(root: str | Path, workspace_id: str, name: str) -> Path:
    clean = sanitize_workspace_name(name)
    suffix = re.sub(r"[^A-Za-z0-9]+", "", str(workspace_id or ""))[:8] or "workspace"
    return Path(root) / f"{clean}__{suffix}"


def ensure_workspace_layout(root: str | Path, workspace_id: str, name: str) -> dict[str, Path]:
    base = workspace_dir(root, workspace_id, name)
    base.mkdir(parents=True, exist_ok=True)
    result = {"root": base}
    for folder in _ALL_DIRS:
        path = base / folder
        path.mkdir(parents=True, exist_ok=True)
        result[folder] = path
    return result


def clean_workspace_results(path: str | Path) -> None:
    """Clear generated workspace content while preserving the dedicated Excel bucket."""
    base = Path(path)
    base.mkdir(parents=True, exist_ok=True)
    excel = base / "Excel"
    excel.mkdir(parents=True, exist_ok=True)
    for child in list(base.iterdir()):
        if child == excel:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    for folder in _RESULT_DIRS:
        (base / folder).mkdir(parents=True, exist_ok=True)


def delete_workspace_files(path: str | Path) -> None:
    target = Path(path)
    if target.exists():
        shutil.rmtree(target)
