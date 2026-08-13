from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, Any] = {
    "ocr_space_enabled": True,
    "mistral_enabled": True,
    "mistral_model": "mistral-small-latest",
    "request_timeout": 20,
}


def default_settings_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or Path.home() / ".product_intelligence")
    return base / "ProductIntelligence" / "settings.json"


class ProviderSettings:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_settings_path()
        self._values = dict(DEFAULTS)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if isinstance(raw, dict):
            for key in DEFAULTS:
                if key in raw:
                    self._values[key] = raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(f"Ajuste desconocido: {key}")
        self._values[key] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._values, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)
