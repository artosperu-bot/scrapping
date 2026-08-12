from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def format_money(value: float | int | None, currency: str | None) -> str:
    if value is None:
        return ""
    code = str(currency or "").upper().strip() or "PEN"
    amount = float(value)
    if code == "PEN":
        return f"S/ {amount:,.2f}"
    if code == "USD":
        return f"US$ {amount:,.2f}"
    if code in {"CLP", "COP"}:
        return f"{code} {amount:,.0f}"
    return f"{code} {amount:,.2f}"


@dataclass(slots=True)
class PriceOffer:
    part_number: str | None
    brand: str | None
    model: str | None
    channel: str
    seller_display_name: str | None
    selling_price: float
    currency: str
    url: str
    confidence: float
    identity_match: str
    source_type: str
    source_method: str
    list_price: float | None = None
    stock: int | None = None
    availability: str | None = None
    condition: str | None = None
    payment_method: str | None = None
    seller_legal_name: str | None = None
    seller_tax_id: str | None = None
    publication_id: str | None = None
    sku: str | None = None
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
