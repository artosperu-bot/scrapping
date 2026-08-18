from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement target, got {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# P1: reject generic product/category phrases as brands, not one benchmark literal.
replace_once(
    "src/product_intelligence/identity_bootstrap.py",
    "_SECOND_TOKEN_DESCRIPTORS = {",
    '''_GENERIC_PRODUCT_TYPE_WORDS = {
    # Generic ecommerce/category vocabulary in English and Spanish. These words
    # can describe a product class but cannot independently prove a manufacturer.
    "product", "producto", "productos", "item", "articulo", "artículo", "compra", "comprar",
    "disco", "duro", "unidad", "almacenamiento", "storage", "drive", "ssd", "hdd",
    "memoria", "memory", "ram", "laptop", "notebook", "monitor", "mouse", "teclado", "keyboard",
    "audifono", "audífono", "audifonos", "audífonos", "headphone", "headphones", "speaker", "parlante",
    "celular", "telefono", "teléfono", "smartphone", "tablet", "televisor", "tv", "camera", "cámara",
    "impresora", "printer", "router", "cable", "adaptador", "adapter", "cargador", "charger",
    "herramienta", "tool", "taladro", "drill", "juguete", "toy", "perfume", "belleza", "beauty",
    "electrodomestico", "electrodoméstico", "appliance", "repuesto", "accesorio", "accessory",
}

_SECOND_TOKEN_DESCRIPTORS = {''',
)
replace_once(
    "src/product_intelligence/identity_bootstrap.py",
    'generic_keys = {_compact(value) for value in (*_GENERIC_BRAND_WORDS, *_CONTEXT_STOPWORDS)}',
    'generic_keys = {_compact(value) for value in (*_GENERIC_BRAND_WORDS, *_CONTEXT_STOPWORDS, *_GENERIC_PRODUCT_TYPE_WORDS)}',
)

# P1 identifier typing: GTIN must come only from explicit GTIN fields; SKU remains SKU.
replace_once(
    "src/product_intelligence/price_discovery.py",
    "from .models import ProductIdentity\n",
    "from .models import ProductIdentity\nfrom .identifiers import canonical_gtin, clean_identifier_value\n",
)
replace_once(
    "src/product_intelligence/price_discovery.py",
    '"gtin": node.get("gtin13") or node.get("gtin12") or node.get("gtin") or node.get("sku"),',
    '"gtin": canonical_gtin(node.get("gtin14") or node.get("gtin13") or node.get("gtin12") or node.get("gtin8") or node.get("gtin")),\n                "sku": clean_identifier_value(node.get("sku")),',
)
replace_once(
    "src/product_intelligence/price_discovery.py",
    'sku=str(node.get("sku") or "") or None,',
    'sku=clean_identifier_value(node.get("sku")),',
)

# P2: enforce directed-domain constraint before ranking so an off-domain result
# cannot displace a valid in-domain PDP.
replace_once(
    "src/product_intelligence/discovery.py",
    '''def _budgeted_query(identity:ProductIdentity,query:str,timeout:int,tracker:SearchBudgetTracker)->list[SearchCandidate]:
    if not query or not tracker.reserve_query():return []
    rows=_provider_search(query,timeout)
    ranked=_rank_candidates(rows,identity,tracker.budget.max_candidates_per_query)
    tracker.admit_candidates(len(ranked))
    return ranked


def search_web_query(identity:ProductIdentity,query:str,limit:int=6,timeout:int=8,budget_tracker:SearchBudgetTracker|None=None)->list[str]:
    if not str(query or "").strip():return []
    if budget_tracker is not None:
        ranked=_budgeted_query(identity,str(query).strip(),timeout,budget_tracker)
    else:
        ranked=_rank_candidates(_provider_search(str(query).strip(),timeout),identity,max(limit*2,limit))
    return [row.url for row in ranked[:limit]]
''',
    '''def _provider_rows_for_domain(rows:list[tuple[str,str,str]],required_domain:str|None)->list[tuple[str,str,str]]:
    domain=str(required_domain or "").lower().removeprefix("www.").strip()
    if not domain:return rows
    out=[]
    for row in rows:
        host=(urlparse(row[0]).hostname or "").lower().removeprefix("www.")
        if host==domain or host.endswith("."+domain):out.append(row)
    return out


def _budgeted_query(identity:ProductIdentity,query:str,timeout:int,tracker:SearchBudgetTracker,required_domain:str|None=None)->list[SearchCandidate]:
    if not query or not tracker.reserve_query():return []
    rows=_provider_rows_for_domain(_provider_search(query,timeout),required_domain)
    ranked=_rank_candidates(rows,identity,tracker.budget.max_candidates_per_query)
    tracker.admit_candidates(len(ranked))
    return ranked


def search_web_query(identity:ProductIdentity,query:str,limit:int=6,timeout:int=8,budget_tracker:SearchBudgetTracker|None=None,required_domain:str|None=None)->list[str]:
    if not str(query or "").strip():return []
    if budget_tracker is not None:
        ranked=_budgeted_query(identity,str(query).strip(),timeout,budget_tracker,required_domain=required_domain)
    else:
        rows=_provider_rows_for_domain(_provider_search(str(query).strip(),timeout),required_domain)
        ranked=_rank_candidates(rows,identity,max(limit*2,limit))
    return [row.url for row in ranked[:limit]]
''',
)

# P3: stop on bounded coverage, not merely because the first query found one PDP.
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    "urls = search_web_query(identity, query, limit=limit_per_domain, timeout=12)",
    "urls = search_web_query(identity, query, limit=limit_per_domain, timeout=12, required_domain=domain)",
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    "        if found:\n            break\n    if not found and model:\n",
    "        if len(found) >= limit_per_domain:\n            break\n    if len(found) < limit_per_domain and model:\n",
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    "urls = search_web_query(alias_identity, query, limit=limit_per_domain, timeout=12)",
    "urls = search_web_query(alias_identity, query, limit=limit_per_domain, timeout=12, required_domain=domain)",
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    "            if found:\n                break\n    return found\n",
    "            if len(found) >= limit_per_domain:\n                break\n    return found\n",
)

print("UNIVERSAL_PRICE_RECALL_CORE_PATCH=APPLIED")
