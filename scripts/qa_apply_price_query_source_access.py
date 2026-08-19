from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement target, got {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# P2 — Mercado Libre consumes the same bounded universal identity-signal plan.
replace_once(
    "src/product_intelligence/price_workflow.py",
    "from .price_models import PriceOffer\n",
    "from .price_models import PriceOffer\nfrom .price_queries import build_price_query_plan\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '''def _mercadolibre_queries(identity: ProductIdentity) -> list[str]:
    values = [
        _query(identity),
        " ".join(v for v in (identity.brand, identity.model or identity.product_name) if v).strip(),
        str(identity.model or identity.product_name or "").strip(),
    ]
    return list(dict.fromkeys(v for v in values if v))
''',
    '''def _mercadolibre_queries(identity: ProductIdentity) -> list[str]:
    return [row.query for row in build_price_query_plan(identity, limit=12)]
''',
)

# P2 domain-awareness also applies to the older targeted discovery lane.
replace_once(
    "src/product_intelligence/price_discovery.py",
    "found = search_web_query(identity, query, limit=limit_per_domain, timeout=12)",
    "found = search_web_query(identity, query, limit=limit_per_domain, timeout=12, required_domain=domain)",
)

# P5.5 — generic HTML fallback ignores installment/shipping/unit-money values.
replace_once(
    "src/product_intelligence/price_discovery.py",
    '''def _seller_from_text(text: str) -> str | None:
''',
    '''_NON_PRODUCT_PRICE_CONTEXT = (
    "cuota", "cuotas", "mensual", "al mes", "por mes", "envío", "envio", "delivery", "shipping",
    "despacho", "por kg", "/kg", "kilogram", "precio por unidad", "unit price", "financiamiento",
)
_PRODUCT_PRICE_CONTEXT = ("precio internet", "precio online", "precio oferta", "precio", "oferta", "ahora", "venta")


def _visible_product_price(text: str) -> float | None:
    candidates = []
    for match in re.finditer(r"(?:S/\\.?|S\\s*/|PEN\\s*)\\s*([0-9]{1,7}(?:[.,][0-9]{1,2})?)", text or "", re.I):
        price = _money(match.group(1))
        if not price or price <= 0:
            continue
        start = max(0, match.start() - 70)
        end = min(len(text), match.end() + 70)
        context = text[start:end].casefold()
        if any(marker in context for marker in _NON_PRODUCT_PRICE_CONTEXT):
            continue
        positive = sum(1 for marker in _PRODUCT_PRICE_CONTEXT if marker in context)
        candidates.append((positive, match.start(), price))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (-row[0], row[1]))
    return candidates[0][2]


def _seller_from_text(text: str) -> str | None:
''',
)
replace_once(
    "src/product_intelligence/price_discovery.py",
    '''    if not meta_price:
        match_price = re.search(r"(?:S/\\.?|S\\s*/|PEN\\s*)\\s*([0-9]{1,6}(?:[.,][0-9]{1,2})?)", page_text, re.I)
        meta_price = _money(match_price.group(1)) if match_price else None
''',
    '''    if not meta_price:
        meta_price = _visible_product_price(page_text)
''',
)

print("PRICE_QUERY_SOURCE_ACCESS_PATCH=APPLIED")
