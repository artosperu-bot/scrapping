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


old_queries = '''    aliases = _identifier_aliases(strong) or ([strong] if strong else [])
    q: list[str] = []
    for alias in aliases:
        q.append(f'"{alias}" site:{domain}')
        if brand:
            q.append(f'"{alias}" "{brand}" site:{domain}')
        if model:
            q.append(f'"{alias}" "{model}" site:{domain}')
    if model:
        q.append(f'"{model}" "{brand}" site:{domain}'.strip())
'''
new_queries = '''    aliases = _identifier_aliases(strong) or ([strong] if strong else [])
    q: list[str] = []
    original = aliases[0] if aliases else strong
    compact = next((alias for alias in aliases[1:] if not any(ch in alias for ch in "/- ")), None)
    # Information-gain order: exact supplied value, compact separator alias, then
    # verified semantic context. Remaining aliases are fallbacks, never case-only copies.
    if original:
        q.append(f'"{original}" site:{domain}')
    if compact and compact.casefold() != str(original or "").casefold():
        q.append(f'"{compact}" site:{domain}')
    if original and brand:
        q.append(f'"{original}" "{brand}" site:{domain}')
    if original and model:
        q.append(f'"{original}" "{model}" site:{domain}')
    for alias in aliases[1:]:
        if compact and alias.casefold() == compact.casefold():
            continue
        q.append(f'"{alias}" site:{domain}')
        if brand:
            q.append(f'"{alias}" "{brand}" site:{domain}')
    if model:
        q.append(f'"{model}" "{brand}" site:{domain}'.strip())
'''
replace_once("src/product_intelligence/price_peru_coverage.py", old_queries, new_queries)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    "def _discover_target_domain(identity: ProductIdentity, domain: str, limit_per_domain: int, *, on_event=None, max_queries: int = 6) -> list[str]:",
    "def _discover_target_domain(identity: ProductIdentity, domain: str, limit_per_domain: int, *, on_event=None, max_queries: int = 3) -> list[str]:",
)

old_general = '''def discover_general_peru_retailers(identity: ProductIdentity, *, limit: int = 20, on_event=None) -> list[str]:
    strong = _strong(identity)
    if not strong or limit <= 0:
        return []
    rows: list[str] = []
    seen: set[str] = set()
    per_query = max(6, min(20, limit * 2))

    exact_batches = _search_query_batches(identity, _general_retail_queries(identity), per_query, on_event=on_event)
    if _append_retail_candidates(rows, seen, exact_batches, strong, limit):
        return rows

    model = str(identity.model or identity.product_name or "").strip()
    if model and len(rows) < limit:
        alias_identity = _alias_identity(identity)
        alias_batches = _search_query_batches(alias_identity, _general_alias_queries(identity), per_query, on_event=on_event)
        _append_retail_candidates(rows, seen, alias_batches, model, limit)
    return rows
'''
new_general = '''def _progressive_general_query_plan(identity: ProductIdentity) -> list[tuple[ProductIdentity, str, str]]:
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


def discover_general_peru_retailers(identity: ProductIdentity, *, limit: int = 20, on_event=None, max_queries: int = 14) -> list[str]:
    strong = _strong(identity)
    if not strong or limit <= 0 or max_queries <= 0:
        return []
    rows: list[str] = []
    seen: set[str] = set()
    seen_domains: set[str] = set()
    per_query = max(6, min(20, limit * 2))
    no_gain_streak = 0
    plan = _progressive_general_query_plan(identity)
    query_count = 0
    stop_reason = "query_plan_exhausted"

    def emit(stage: str, **payload) -> None:
        if on_event:
            on_event({"stage": stage, "lane": "open_peru_retail", **payload})

    for search_identity, query, marker in plan:
        if query_count >= max_queries:
            stop_reason = "query_budget_exhausted"
            break
        query_count += 1
        before_rows = len(rows)
        before_domains = set(seen_domains)
        batches = _search_query_batches(search_identity, [query], per_query, on_event=on_event)
        _append_retail_candidates(rows, seen, batches, marker, limit)
        seen_domains.update(_host(url) for url in rows if _host(url))
        new_pdps = len(rows) - before_rows
        new_domains = len(seen_domains - before_domains)
        emit(
            "QUERY_INFORMATION_GAIN",
            query=query,
            new_urls=new_pdps,
            new_pdps=new_pdps,
            new_domains=new_domains,
            new_sellers=0,
            new_marketplace_listings=0,
            accepted_products=new_pdps,
            total_pdps=len(rows),
            information_gain=new_pdps + new_domains,
        )
        no_gain_streak = 0 if (new_pdps or new_domains) else no_gain_streak + 1
        if len(rows) >= limit:
            stop_reason = "candidate_budget_full"
            break
        if rows and no_gain_streak >= 3:
            stop_reason = "no_new_pdps"
            break
    else:
        if len(plan) > max_queries:
            stop_reason = "query_budget_exhausted"

    emit("DISCOVERY_STOP", reason=stop_reason, queries=query_count, total_pdps=len(rows), domains=len(seen_domains))
    return rows[:limit]
'''
replace_once("src/product_intelligence/price_peru_coverage.py", old_general, new_general)

print("PROGRESSIVE_PRICE_BUDGET_PATCH=APPLIED")
