from __future__ import annotations

from pathlib import Path
from typing import Any


def detect_platform(_url: str, _html: str) -> str:
    return "custom"


class SourceCapabilityRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def observe(self, _url: str, **_kwargs: Any) -> None:
        return None

    def save(self) -> None:
        return None

    def get(self, _domain: str) -> dict[str, Any] | None:
        return None
