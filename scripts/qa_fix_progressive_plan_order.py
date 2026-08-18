from __future__ import annotations

from pathlib import Path

path = Path("src/product_intelligence/price_peru_coverage.py")
text = path.read_text(encoding="utf-8")
old = '''def _progressive_general_query_plan(identity: ProductIdentity) -> list[tuple[ProductIdentity, str, str]]:
    strong = _strong(identity)
    if not strong:
        return []
    brand = str(identity.brand or "").strip()
    model = str(identity.model or identity.product_name or "").strip()
    aliases = _identifier_aliases(strong) or [strong]
    original = aliases[0]
    compact = next((alias for alias in aliases[1:] if not any(ch in alias for ch in "/- ")), None)
    plan: list[tuple[ProductIdentity, str, str]] = []

    def add(search_identity: ProductIdentity, query: str, marker: str) -> None:
        text = str(query or "").strip()
        if text and text not in {row[1] for row in plan}:
            plan.append((search_identity, text, marker))

    for suffix in ("precio Perú", '"S/" Perú', "tienda Perú", "comprar Perú"):
        add(identity, f'"{original}" {suffix}', strong)
    if compact and compact.casefold() != original.casefold():
        add(identity, f'"{compact}" precio Perú', strong)
        add(identity, f'"{compact}" "S/" Perú', strong)
    if brand:
        add(identity, f'"{original}" "{brand}" Perú', strong)
    if model:
        add(identity, f'"{original}" "{model}" Perú', strong)
        alias_identity = _alias_identity(identity)
        add(alias_identity, f'"{model}" "{brand}" precio Perú'.strip(), model)

    # Known-source queries are a late bounded lane. They do not crowd out open-web
    # discovery and are never expanded for every separator alias.
    for domain in PERU_RETAIL_HINT_DOMAINS:
        add(identity, f'"{original}" site:{domain}', strong)
    return plan
'''
new = '''def _progressive_general_query_plan(identity: ProductIdentity) -> list[tuple[ProductIdentity, str, str]]:
    strong = _strong(identity)
    if not strong:
        return []
    brand = str(identity.brand or "").strip()
    model = str(identity.model or identity.product_name or "").strip()
    aliases = _identifier_aliases(strong) or [strong]
    original = aliases[0]
    compact = next((alias for alias in aliases[1:] if not any(ch in alias for ch in "/- ")), None)
    plan: list[tuple[ProductIdentity, str, str]] = []

    def add(search_identity: ProductIdentity, query: str, marker: str) -> None:
        query_text = str(query or "").strip()
        if query_text and query_text not in {row[1] for row in plan}:
            plan.append((search_identity, query_text, marker))

    # High-information open-web queries first. Case-only aliases are never generated.
    add(identity, f'"{original}" precio Perú', strong)
    add(identity, f'"{original}" "S/" Perú', strong)
    if compact and compact.casefold() != original.casefold():
        add(identity, f'"{compact}" precio Perú', strong)
    if brand:
        add(identity, f'"{original}" "{brand}" Perú', strong)
    if model:
        add(identity, f'"{original}" "{model}" Perú', strong)
        alias_identity = _alias_identity(identity)
        add(alias_identity, f'"{model}" "{brand}" precio Perú'.strip(), model)
        # A retailer can publish a valid PDP without the manufacturer identifier in
        # the URL/title. Preserve that former fallback inside the same global budget.
        for domain in PERU_RETAIL_HINT_DOMAINS:
            add(alias_identity, f'"{model}" "{brand}" site:{domain}'.strip(), model)

    # If model evidence is unavailable, exact identifier site queries remain early.
    # If a model exists they follow the model-aware specialist lane instead of
    # consuming the entire budget before it can run.
    for domain in PERU_RETAIL_HINT_DOMAINS:
        add(identity, f'"{original}" site:{domain}', strong)

    # Broad low-yield variants are last-resort fallbacks only.
    add(identity, f'"{original}" tienda Perú', strong)
    add(identity, f'"{original}" comprar Perú', strong)
    if compact and compact.casefold() != original.casefold():
        add(identity, f'"{compact}" "S/" Perú', strong)
    return plan
'''
if new not in text:
    if old not in text:
        raise RuntimeError("progressive query plan block not found after primary patch")
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
print("PROGRESSIVE_PLAN_ORDER_FIX=APPLIED")
