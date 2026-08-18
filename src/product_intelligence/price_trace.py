from __future__ import annotations

from typing import Any


class PriceTrace:
    """Price diagnostic trace API; behavior is added only after RED is observed."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, stage: str, **payload: Any) -> None:
        self.events.append({"stage": str(stage), **payload})

    def coverage(self, _offers) -> dict[str, Any]:
        return {"channels": [], "individual_stores": []}
