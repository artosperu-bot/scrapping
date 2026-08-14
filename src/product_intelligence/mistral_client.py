from __future__ import annotations

from typing import Any, Protocol


class MistralTransport(Protocol):
    def generate(self, payload: dict[str, Any], *, model: str, timeout: int) -> str:
        ...


class MistralClient:
    """Transport seam for Mistral narration.

    The real authenticated transport is intentionally not wired in this phase.
    Tests inject a fake transport; production falls back deterministically until
    real credentials/provider validation are explicitly enabled in a later phase.
    """

    def generate(self, payload: dict[str, Any], *, model: str, timeout: int) -> str:
        raise RuntimeError("Mistral transport not configured")
