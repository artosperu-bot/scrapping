from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .discovery import search_web_query
from .models import ProductIdentity
from .price_channel_registry import TARGET_CHANNELS

PERU_TARGET_DOMAINS: tuple[str, ...] = tuple(dict.fromkeys(
    domain for spec in TARGET_CHANNELS for domain in spec.domains
))
PERU_MARKETPLACE_DOMAINS: tuple[str, ...] = PERU_TARGET_DOMAINS + ("jbl.com.pe",)
PERU_RETAIL_HINT_DOMAINS: tuple[str, ...] = (
    "infiniti.com.pe", "perudataconsult.net", "arteus.pe", "baetech.pe",
    "panacompu.com", "memorykings.pe", "estuyo.pe", "bigmarketperu.com", "efe.com.pe",
)
TARGET_DISCOVERY_WORKERS = 4
RETAIL_QUERY_WORKERS = 4
_LISTING_MARKERS = ("/category/", "/categoria/", "/search/", "/buscar/", "/landing/", "/collections/", "/pages/", "/lista/")
# /product intentionally covers product/products/producto/productos.
_PRODUCT_MARKERS = ("/product", "/shop/", "/informacion-producto/", "/product-information/", "/articulo/")


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _host_matches(url: str, domain: str) -> bool:
    host = _host(url)
    return host == domain or host.endswith("." + domain)


def _strong_identifiers(identity: ProductIdentity) -> list[str]:
    out, seen = [], set()
    for value in (identity.mpn, identity.ean, identity.upc, identity.gtin):
        clean = str(value or "").strip()
        key = _compact(clean)
        if clean and key and key not in seen:
            seen.add(key)
            out.append(clean)
    return out


def _identifier_aliases(value: str | None) -> list[str]:
    original = str(value or "").strip()
    if not original:
        return []
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", original) if part]
    aliases = [original]
    if len(parts) >= 2:
        aliases.extend(["".join(parts), "-".join(parts), " ".join(parts)])
    out, seen = [], set()
    for alias in aliases:
        key = alias.casefold()
        if alias and key not in seen:
            seen.add(key)
            out.append(alias)
    return out


def _strong(identity: ProductIdentity) -> str:
    ids = _strong_identifiers(identity)
    return ids[0] if ids else str(identity.model or identity.product_name or "").strip()


def _alias_identity(identity: ProductIdentity) -> ProductIdentity:
    """Discovery-only identity: retain semantics but remove strong IDs from search ranking."""
    data = identity.model_dump()
    for field in ("mpn", "ean", "upc", "gtin", "sku"):
        data[field] = None
    return ProductIdentity(**data)


def _is_pdp(url: str, domain: str, strong: str) -> bool:
    path = (urlparse(url).path or "").lower()
    if any(marker in path for marker in _LISTING_MARKERS):
        return False
    if domain == "falabella.com.pe": return "/product/" in path
    if domain in {"simple.ripley.com.pe", "ripley.com.pe"}: return "pmp" in path or _compact(strong) in _compact(path)
    if domain == "mercadolibre.com.pe": return "/p/" in path or "/up/" in path
    if domain in {"plazavea.com.pe", "oechsle.pe", "realplaza.com", "tienda.claro.com.pe", "claro.com.pe"}: return path.rstrip("/").endswith("/p") or any(marker in path for marker in _PRODUCT_MARKERS)
    if domain == "sodimac.com.pe": return "/articulo/" in path
    if domain == "jbl.com.pe": return bool(_compact(strong) and _compact(strong) in _compact(path))
    return bool(any(marker in path for marker in _PRODUCT_MARKERS) or path.rstrip("/").endswith("/p") or path.endswith(".html"))


def _deterministic_pdps(identity: ProductIdentity) -> list[str]:
    if _compact(identity.brand) == "jbl" and identity.mpn:
        return [f"https://www.jbl.com.pe/{str(identity.mpn).strip()}.html"]
    return []


def _queries(identity: ProductIdentity, domain: str) -> list[str]:
    strong = _strong(identity)
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    aliases = _identifier_aliases(strong) or ([strong] if strong else [])
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
    extras = {
        "falabella.com.pe": [
            f'"{strong}" site:falabella.com.pe/falabella-pe/product',
            f'"{strong}" "Vendido por" site:falabella.com.pe',
            f'"{strong}" "Modelo" site:falabella.com.pe/falabella-pe/product'],
        "simple.ripley.com.pe": [
            f'"{strong}" site:simple.ripley.com.pe pmp',
            f'"{strong}" "Vendido por" site:simple.ripley.com.pe',
            f'"{strong}" "Internet" site:simple.ripley.com.pe',
            f'"{model}" "Internet" site:simple.ripley.com.pe pmp' if model else ""],
        "mercadolibre.com.pe": [
            f'"{strong}" site:mercadolibre.com.pe/p', f'"{strong}" site:mercadolibre.com.pe/up',
            f'"{strong}" "Modelo alfanumérico" site:mercadolibre.com.pe',
            f'"{strong}" "Modelo detallado" site:mercadolibre.com.pe'],
        "plazavea.com.pe": [f'"{strong}" site:plazavea.com.pe "/p"', f'"{strong}" "Vendido por" site:plazavea.com.pe'],
        "oechsle.pe": [f'"{strong}" site:oechsle.pe "/p"', f'"{strong}" "Vendido por" site:oechsle.pe'],
        "sodimac.com.pe": [f'"{strong}" site:sodimac.com.pe/sodimac-pe/articulo'],
        "jbl.com.pe": [f'"{model}" site:jbl.com.pe'] if model else [],
    }
    q += extras.get(domain, [])
    return list(dict.fromkeys(x for x in q if x.strip()))


def _alias_queries(identity: ProductIdentity, domain: str) -> list[str]:
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    if not model:
        return []
    return list(dict.fromkeys([
        f'"{model}" "{brand}" site:{domain}'.strip(),
        f'"{model}" site:{domain}',
    ]))


def _discover_target_domain(identity: ProductIdentity, domain: str, limit_per_domain: int, *, on_event=None, max_queries: int = 3) -> list[str]:
    strong = _strong(identity)
    model = str(identity.model or identity.product_name or "").strip()
    alias_identity = _alias_identity(identity)
    found: list[str] = []
    seen: set[str] = set()
    query_count = 0
    no_gain_streak = 0

    def emit(stage: str, **payload) -> None:
        if on_event:
            on_event({"stage": stage, "domain": domain, **payload})

    for seed in _deterministic_pdps(identity):
        if _host_matches(seed, domain) and _is_pdp(seed, domain, strong):
            seen.add(seed)
            found.append(seed)
    if len(found) >= limit_per_domain:
        emit("DISCOVERY_STOP", reason="candidate_budget_full", total_pdps=len(found), queries=query_count)
        return found[:limit_per_domain]

    plans = [(identity, query, strong) for query in _queries(identity, domain)]
    if model:
        plans.extend((alias_identity, query, model) for query in _alias_queries(identity, domain))

    stop_reason = "query_plan_exhausted"
    for query_identity, query, marker in plans:
        if query_count >= max_queries:
            stop_reason = "query_budget_exhausted"
            break
        query_count += 1
        before = len(found)
        try:
            urls = search_web_query(query_identity, query, limit=limit_per_domain, timeout=12, on_event=on_event)
        except Exception as exc:
            urls = []
            emit("QUERY_EXECUTED", query=query, raw_results=None, valid_in_domain=None, ranked_results=0, error=f"{type(exc).__name__}: {exc}")
        for raw in urls:
            url = str(raw or "").strip()
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            if not _host_matches(url, domain) or not _is_pdp(url, domain, marker):
                continue
            seen.add(url)
            found.append(url)
            if len(found) >= limit_per_domain:
                break
        gain = len(found) - before
        emit("QUERY_INFORMATION_GAIN", query=query, new_urls=gain, new_pdps=gain, total_pdps=len(found), information_gain=gain)
        no_gain_streak = 0 if gain else no_gain_streak + 1
        if len(found) >= limit_per_domain:
            stop_reason = "candidate_budget_full"
            break
        if found and no_gain_streak >= 2:
            stop_reason = "no_new_pdps"
            break
    emit("DISCOVERY_STOP", reason=stop_reason, total_pdps=len(found), queries=query_count)
    return found


def discover_additional_peru_pdps(identity: ProductIdentity, *, limit_per_domain: int = 10, domains: tuple[str, ...] = PERU_MARKETPLACE_DOMAINS, on_event=None) -> list[str]:
    strong = _strong(identity)
    if not strong or not domains:
        return []
    workers = max(1, min(TARGET_DISCOVERY_WORKERS, len(domains)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="peru-channel") as pool:
        per_domain = list(pool.map(lambda domain: _discover_target_domain(identity, domain, limit_per_domain, on_event=on_event), domains))
    merged, seen_all = [], set()
    for index in range(limit_per_domain):
        for rows in per_domain:
            if index < len(rows) and rows[index] not in seen_all:
                seen_all.add(rows[index])
                merged.append(rows[index])
    return merged


def _is_peru_retail_candidate(url: str, strong: str) -> bool:
    path, host = (urlparse(url).path or "").lower(), _host(url)
    if not host or any(marker in path for marker in _LISTING_MARKERS): return False
    if any(_host_matches(url, domain) for domain in PERU_MARKETPLACE_DOMAINS): return False
    local = host.endswith(".pe") or host.endswith(".com.pe")
    hinted = any(_host_matches(url, domain) for domain in PERU_RETAIL_HINT_DOMAINS)
    peru_path = path.startswith("/peru")
    if not (local or hinted or peru_path): return False
    return bool((_compact(strong) and _compact(strong) in _compact(url)) or any(marker in path for marker in _PRODUCT_MARKERS))


def _general_retail_queries(identity: ProductIdentity) -> list[str]:
    ids = _strong_identifiers(identity) or ([_strong(identity)] if _strong(identity) else [])
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    q = []
    for strong in ids:
        for alias in _identifier_aliases(strong):
            q += [f'"{alias}" precio Perú', f'"{alias}" "S/" Perú', f'"{alias}" tienda Perú', f'"{alias}" comprar Perú']
            if model: q += [f'"{alias}" "{model}" Perú', f'"{model}" "{alias}" {brand} Perú'.strip()]
            q += [f'"{alias}" site:{domain}' for domain in PERU_RETAIL_HINT_DOMAINS]
    return list(dict.fromkeys(x for x in q if x.strip()))


def _general_alias_queries(identity: ProductIdentity) -> list[str]:
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    if not model:
        return []
    queries = [f'"{model}" "{brand}" precio Perú'.strip(), f'"{model}" "{brand}" tienda Perú'.strip()]
    queries += [f'"{model}" "{brand}" site:{domain}'.strip() for domain in PERU_RETAIL_HINT_DOMAINS]
    return list(dict.fromkeys(queries))


def _search_query_batches(identity: ProductIdentity, queries: list[str], per_query: int, on_event=None) -> list[list[str]]:
    if not queries:
        return []
    workers = max(1, min(RETAIL_QUERY_WORKERS, len(queries)))
    def run(query: str) -> list[str]:
        try:
            return search_web_query(identity, query, limit=per_query, timeout=12, on_event=on_event)
        except Exception:
            return []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="peru-retail") as pool:
        return list(pool.map(run, queries))


def _append_retail_candidates(rows: list[str], seen: set[str], batches: list[list[str]], marker: str, limit: int) -> bool:
    for found in batches:
        for raw in found:
            url = str(raw or "").strip()
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            if not _is_peru_retail_candidate(url, marker):
                continue
            seen.add(url)
            rows.append(url)
            if len(rows) >= limit:
                return True
    return False


def _progressive_general_query_plan(identity: ProductIdentity) -> list[tuple[ProductIdentity, str, str]]:
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
