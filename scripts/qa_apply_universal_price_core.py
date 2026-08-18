from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"expected source block not found: {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# P0 semantic baseline: absence of an accepted offer is not proof that a source has no product.
replace_once(
    "src/product_intelligence/price_channel_registry.py",
    '            "status": "FOUND" if rows else "NO_HAY",',
    '            "status": "FOUND" if rows else "NOT_SEARCHED",',
)

# P1: generic product/category/navigation vocabulary cannot be promoted to a brand merely
# because the same SERP wording repeats across domains. This is deliberately category-
# generic rather than benchmark-specific.
replace_once(
    "src/product_intelligence/identity_bootstrap.py",
    '    "sensor", "sensors", "adapter", "charger", "camera", "speaker", "television",\n}',
    '    "sensor", "sensors", "adapter", "charger", "camera", "speaker", "television",\n'
    '    "disco", "duro", "unidad", "estado", "solido", "sólido", "almacenamiento", "ssd", "hdd",\n'
    '    "memoria", "memory", "celular", "telefono", "teléfono", "smartphone", "tablet", "monitor",\n'
    '    "laptop", "notebook", "computer", "computadora", "mouse", "keyboard", "teclado", "audifono",\n'
    '    "audífono", "auricular", "headphone", "headphones", "parlante", "router", "printer", "impresora",\n'
    '    "cable", "cargador", "charger", "televisor", "tv", "herramienta", "tool", "taladro", "drill",\n'
    '    "perfume", "juguete", "toy", "pañal", "panal", "compra", "comprar", "venta", "precio", "producto",\n'
    '}',
)

# P1 identifier integrity: JSON-LD SKU is seller/product SKU evidence, never implicit GTIN.
replace_once(
    "src/product_intelligence/price_discovery.py",
    '                "gtin": node.get("gtin13") or node.get("gtin12") or node.get("gtin") or node.get("sku"),',
    '                "gtin": node.get("gtin13") or node.get("gtin12") or node.get("gtin14") or node.get("gtin8") or node.get("gtin"),',
)

# P2 directed search: honor a site: constraint before ranking so off-domain results cannot
# displace an in-domain PDP. The helper is also used by budgeted queries.
replace_once(
    "src/product_intelligence/discovery.py",
    'def _budgeted_query(identity:ProductIdentity,query:str,timeout:int,tracker:SearchBudgetTracker)->list[SearchCandidate]:\n'
    '    if not query or not tracker.reserve_query():return []\n'
    '    rows=_provider_search(query,timeout)\n'
    '    ranked=_rank_candidates(rows,identity,tracker.budget.max_candidates_per_query)\n'
    '    tracker.admit_candidates(len(ranked))\n'
    '    return ranked\n\n\n'
    'def search_web_query(identity:ProductIdentity,query:str,limit:int=6,timeout:int=8,budget_tracker:SearchBudgetTracker|None=None)->list[str]:\n'
    '    if not str(query or "").strip():return []\n'
    '    if budget_tracker is not None:\n'
    '        ranked=_budgeted_query(identity,str(query).strip(),timeout,budget_tracker)\n'
    '    else:\n'
    '        ranked=_rank_candidates(_provider_search(str(query).strip(),timeout),identity,max(limit*2,limit))\n'
    '    return [row.url for row in ranked[:limit]]',
    'def _query_domain_constraint(query:str)->str|None:\n'
    '    match=re.search(r"\\bsite:([^\\s\\\"\\\'/]+)",str(query or ""),re.I)\n'
    '    if not match:return None\n'
    '    return match.group(1).lower().removeprefix("www.")\n\n\n'
    'def _filter_query_domain(rows:list[tuple[str,str,str]],query:str)->list[tuple[str,str,str]]:\n'
    '    domain=_query_domain_constraint(query)\n'
    '    if not domain:return rows\n'
    '    out=[]\n'
    '    for row in rows:\n'
    '        host=(urlparse(row[0]).hostname or "").lower().removeprefix("www.")\n'
    '        if host==domain or host.endswith("."+domain):out.append(row)\n'
    '    return out\n\n\n'
    'def _budgeted_query(identity:ProductIdentity,query:str,timeout:int,tracker:SearchBudgetTracker)->list[SearchCandidate]:\n'
    '    if not query or not tracker.reserve_query():return []\n'
    '    rows=_filter_query_domain(_provider_search(query,timeout),query)\n'
    '    ranked=_rank_candidates(rows,identity,tracker.budget.max_candidates_per_query)\n'
    '    tracker.admit_candidates(len(ranked))\n'
    '    return ranked\n\n\n'
    'def search_web_query(identity:ProductIdentity,query:str,limit:int=6,timeout:int=8,budget_tracker:SearchBudgetTracker|None=None)->list[str]:\n'
    '    if not str(query or "").strip():return []\n'
    '    if budget_tracker is not None:\n'
    '        ranked=_budgeted_query(identity,str(query).strip(),timeout,budget_tracker)\n'
    '    else:\n'
    '        raw=_filter_query_domain(_provider_search(str(query).strip(),timeout),str(query).strip())\n'
    '        ranked=_rank_candidates(raw,identity,max(limit*2,limit))\n'
    '    return [row.url for row in ranked[:limit]]',
)

# P2 aliases: preserve the original identifier, add safe separator spellings, never add
# a lowercase-only duplicate. Aliases are query strings only, not canonical identity.
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    'def _strong(identity: ProductIdentity) -> str:\n'
    '    ids = _strong_identifiers(identity)\n'
    '    return ids[0] if ids else str(identity.model or identity.product_name or "").strip()\n',
    'def _identifier_aliases(value: str | None) -> list[str]:\n'
    '    original = str(value or "").strip()\n'
    '    if not original:\n'
    '        return []\n'
    '    parts = [part for part in re.split(r"[^A-Za-z0-9]+", original) if part]\n'
    '    aliases = [original]\n'
    '    if len(parts) >= 2:\n'
    '        aliases.extend(["".join(parts), "-".join(parts), " ".join(parts)])\n'
    '    out, seen = [], set()\n'
    '    for alias in aliases:\n'
    '        key = alias.casefold()\n'
    '        if alias and key not in seen:\n'
    '            seen.add(key)\n'
    '            out.append(alias)\n'
    '    return out\n\n\n'
    'def _strong(identity: ProductIdentity) -> str:\n'
    '    ids = _strong_identifiers(identity)\n'
    '    return ids[0] if ids else str(identity.model or identity.product_name or "").strip()\n',
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    '    for strong in ids:\n'
    '        q += [f\'"{strong}" precio Perú\', f\'"{strong}" "S/" Perú\', f\'"{strong}" tienda Perú\', f\'"{strong}" comprar Perú\']\n'
    '        if model: q += [f\'"{strong}" "{model}" Perú\', f\'"{model}" "{strong}" {brand} Perú\'.strip()]\n'
    '        q += [f\'"{strong}" site:{domain}\' for domain in PERU_RETAIL_HINT_DOMAINS]',
    '    for strong in ids:\n'
    '        for alias in _identifier_aliases(strong):\n'
    '            q += [f\'"{alias}" precio Perú\', f\'"{alias}" "S/" Perú\', f\'"{alias}" tienda Perú\', f\'"{alias}" comprar Perú\']\n'
    '            if model: q += [f\'"{alias}" "{model}" Perú\', f\'"{model}" "{alias}" {brand} Perú\'.strip()]\n'
    '            q += [f\'"{alias}" site:{domain}\' for domain in PERU_RETAIL_HINT_DOMAINS]',
)

# P3 stopping: a first PDP is not source saturation. Continue bounded query variants until
# the per-domain candidate budget is full; alias/model fallback may also add candidates.
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    '        if found:\n'
    '            break\n'
    '    if not found and model:',
    '        if len(found) >= limit_per_domain:\n'
    '            break\n'
    '    if len(found) < limit_per_domain and model:',
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    '            if found:\n'
    '                break\n'
    '    return found',
    '            if len(found) >= limit_per_domain:\n'
    '                break\n'
    '    return found',
)

print("UNIVERSAL_PRICE_CORE_PATCH=APPLIED")
