from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_FAILURE_STAGE = {
    "NOT_SEARCHED": "DISCOVERY_NOT_TARGETED",
    "QUERY_EXECUTED_NO_RESULT": "DISCOVERY",
    "RAW_RESULT_FOUND": "DISCOVERY",
    "URL_REJECTED_BY_RANKING": "DISCOVERY_RANKING",
    "URL_REJECTED_BY_DOMAIN": "DISCOVERY_DOMAIN",
    "URL_DISCOVERED": "POST_DISCOVERY",
    "FETCH_STARTED": "ACCESS",
    "FETCH_BLOCKED": "ACCESS",
    "FETCH_NOT_FOUND": "ACCESS",
    "FETCH_TIMEOUT": "ACCESS",
    "ML_NOT_CONFIGURED": "ACCESS",
    "ML_AUTH_FAILED": "ACCESS",
    "ML_ACCESS_BLOCKED": "ACCESS",
    "FETCH_OK": "PARSER_EXTRACTION",
    "PARSER_STARTED": "PARSER_EXTRACTION",
    "PARSER_ZERO_OFFERS": "PARSER_EXTRACTION",
    "IDENTITY_REJECTED": "IDENTITY",
    "IDENTITY_ACCEPTED": "PRICE_EXTRACTION",
    "PRICE_NOT_FOUND": "PRICE_EXTRACTION",
    "PRICE_REJECTED": "FINAL_QUALITY_GATE",
    "OUT_OF_STOCK": None,
    "OFFER_ACCEPTED": None,
    "OFFER_DEDUPED": None,
}

_TERMINAL_POSITIVE = {"OFFER_ACCEPTED", "OUT_OF_STOCK"}


@dataclass(slots=True)
class _SourceState:
    source: str
    status: str = "NOT_SEARCHED"
    failure_stage: str | None = "DISCOVERY_NOT_TARGETED"
    searched: bool = False
    raw_hit: bool = False
    url_found: bool = False
    fetched: bool = False
    fetch_ok: bool = False
    parsed: bool = False
    identity_valid: bool = False
    price_found: bool = False
    stock: bool | None = None
    seller: bool | None = None
    urls: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    def apply(self, status: str, **payload: Any) -> None:
        status = str(status or "").strip().upper()
        if status not in _FAILURE_STAGE:
            raise ValueError(f"Unknown price coverage status: {status}")
        url = str(payload.get("url") or "").strip()
        if url and url not in self.urls:
            self.urls.append(url)
        self.history.append({"status": status, **payload})

        if status != "NOT_SEARCHED":
            self.searched = True
        if status == "RAW_RESULT_FOUND":
            self.raw_hit = True
        if status in {"URL_DISCOVERED", "FETCH_STARTED", "FETCH_OK", "FETCH_BLOCKED", "FETCH_NOT_FOUND", "FETCH_TIMEOUT", "PARSER_STARTED", "PARSER_ZERO_OFFERS", "IDENTITY_ACCEPTED", "IDENTITY_REJECTED", "PRICE_NOT_FOUND", "PRICE_REJECTED", "OUT_OF_STOCK", "OFFER_ACCEPTED", "OFFER_DEDUPED"}:
            self.url_found = True
        if status in {"FETCH_STARTED", "FETCH_OK", "FETCH_BLOCKED", "FETCH_NOT_FOUND", "FETCH_TIMEOUT", "PARSER_STARTED", "PARSER_ZERO_OFFERS", "IDENTITY_ACCEPTED", "IDENTITY_REJECTED", "PRICE_NOT_FOUND", "PRICE_REJECTED", "OUT_OF_STOCK", "OFFER_ACCEPTED", "OFFER_DEDUPED"}:
            self.fetched = True
        if status in {"FETCH_OK", "PARSER_STARTED", "PARSER_ZERO_OFFERS", "IDENTITY_ACCEPTED", "IDENTITY_REJECTED", "PRICE_NOT_FOUND", "PRICE_REJECTED", "OUT_OF_STOCK", "OFFER_ACCEPTED", "OFFER_DEDUPED"}:
            self.fetch_ok = True
        if status in {"PARSER_STARTED", "PARSER_ZERO_OFFERS", "IDENTITY_ACCEPTED", "IDENTITY_REJECTED", "PRICE_NOT_FOUND", "PRICE_REJECTED", "OUT_OF_STOCK", "OFFER_ACCEPTED", "OFFER_DEDUPED"}:
            self.parsed = True
        if status in {"IDENTITY_ACCEPTED", "PRICE_NOT_FOUND", "PRICE_REJECTED", "OUT_OF_STOCK", "OFFER_ACCEPTED", "OFFER_DEDUPED"}:
            self.identity_valid = True
        if status in {"PRICE_REJECTED", "OUT_OF_STOCK", "OFFER_ACCEPTED", "OFFER_DEDUPED"}:
            self.price_found = True
        if status == "OUT_OF_STOCK":
            self.stock = False
        elif status == "OFFER_ACCEPTED" and "stock" in payload:
            self.stock = payload.get("stock")
        if status == "OFFER_ACCEPTED" and "seller" in payload:
            self.seller = bool(payload.get("seller"))

        # A later diagnostic must not downgrade a confirmed accepted/out-of-stock product.
        if self.status in _TERMINAL_POSITIVE and status not in _TERMINAL_POSITIVE:
            return
        self.status = status
        self.failure_stage = _FAILURE_STAGE[status]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "failure_stage": self.failure_stage,
            "searched": self.searched,
            "raw_hit": self.raw_hit,
            "url_found": self.url_found,
            "fetched": self.fetched,
            "fetch_ok": self.fetch_ok,
            "parsed": self.parsed,
            "identity_valid": self.identity_valid,
            "price_found": self.price_found,
            "stock": self.stock,
            "seller": self.seller,
            "urls": list(self.urls),
            "history": list(self.history),
        }


class PriceCoverageTrace:
    """Non-decision telemetry for Price Intelligence source coverage.

    The trace records what the existing engine actually reached. It never decides
    which URL, identity or offer should be accepted.
    """

    def __init__(self) -> None:
        self._states: dict[str, _SourceState] = {}

    def record(self, source: str, status: str, **payload: Any) -> None:
        name = str(source or "Web").strip() or "Web"
        state = self._states.setdefault(name, _SourceState(name))
        state.apply(status, **payload)

    def source_states(self) -> dict[str, dict[str, Any]]:
        return {name: state.as_dict() for name, state in self._states.items()}
