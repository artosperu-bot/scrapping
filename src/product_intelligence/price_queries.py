from __future__ import annotations

from dataclasses import dataclass

from .identifiers import canonical_gtin, clean_identifier_value, mpn_aliases
from .models import ProductIdentity


@dataclass(frozen=True, slots=True)
class PriceQuery:
    query: str
    signal_type: str
    signal_value: str


def build_price_query_plan(identity: ProductIdentity, *, limit: int = 12) -> list[PriceQuery]:
    """Build a small ordered query set from verified identity signals.

    The original MPN is preserved. Separator aliases are useful; case-only aliases
    are intentionally deduplicated. Barcode signals are admitted only when they are
    valid GTIN-family identifiers.
    """
    out: list[PriceQuery] = []
    seen: set[str] = set()

    def add(query: str | None, signal_type: str, signal_value: str | None) -> None:
        clean = str(query or "").strip()
        value = str(signal_value or "").strip()
        key = clean.casefold()
        if not clean or key in seen or len(out) >= max(1, int(limit)):
            return
        seen.add(key)
        out.append(PriceQuery(clean, signal_type, value or clean))

    mpn = clean_identifier_value(identity.mpn)
    if mpn:
        for alias in mpn_aliases(mpn):
            add(alias, "MPN" if alias == mpn else "MPN_ALIAS", mpn)

    brand = str(identity.brand or identity.manufacturer or "").strip()
    if brand and mpn:
        add(f"{brand} {mpn}", "BRAND_MPN", mpn)

    for field_name in ("upc", "ean", "gtin"):
        raw = clean_identifier_value(getattr(identity, field_name, None))
        canonical = canonical_gtin(raw)
        if canonical:
            add(canonical, field_name.upper(), canonical)
            if brand:
                add(f"{brand} {canonical}", f"BRAND_{field_name.upper()}", canonical)

    model = str(identity.model or identity.product_name or "").strip()
    if brand and model:
        add(f"{brand} {model}", "BRAND_MODEL", model)
    elif model:
        add(model, "MODEL", model)

    # Last-resort raw identity inputs when no stronger query exists.
    if not out:
        for field_name in ("sku", "model", "product_name"):
            raw = clean_identifier_value(getattr(identity, field_name, None))
            if raw:
                add(raw, field_name.upper(), raw)

    return out
