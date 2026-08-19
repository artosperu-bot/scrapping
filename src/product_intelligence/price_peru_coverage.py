from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .discovery import search_web_query
from .models import ProductIdentity
from .price_channel_registry import TARGET_CHANNELS
from .price_queries import build_price_query_plan

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


def _query_specs(identity: ProductIdentity, domain: str) -> list[tuple[str, str]]:
    plan = build_price_query_plan(identity, limit=8)
    strong = _strong(identity)
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    specs: list[tuple[str, str]] = [(f'"{row.query}" site:{domain}', row.signal_type) for row in plan]
    if model and strong:
        specs += [
            (f'"{strong}" "{model}" site:{domain}', "MPN_MODEL"),
            (f'"{model}" {brand} site:{domain}'.strip(), "BRAND_MODEL"),
        ]
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
    specs += [(query, "DOMAIN_EXTRA") for query in extras.get(domain, [])]
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for query, signal_type in specs:
        clean = str(query or "").strip()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            out.append((clean, signal_type))
    return out


def _queries(identity: ProductIdentity, domain: str) -> list[str]:
    return [query for query, _signal in _query_specs(identity, domain)]


def _alias_queries(identity: ProductIdentity, domain: str) -> list[str]:
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    if not model:
        return []
    return list(dict.fromkeys([
        f'"{model}" "{brand}" site:{domain}'.strip(),
        f'"{model}" site:{domain}',
    ]))


def _search_with_metrics(identity: ProductIdentity, query: str, *, limit: int, required_domain: str | None = None) -> tuple[list[str], dict]:
    metrics: dict = {}
    kwargs = {"limit": limit, "timeout": 12, "on_metrics": lambda row: metrics.update(row)}
    if required_domain:
        kwargs["required_domain"] = required_domain
    try:
        urls = search_web_query(identity, query, **kwargs)
    except TypeError as exc:
        # Preserve compatibility with legacy injected test/plugin callables while
        # the real search path remains domain-aware and metric-aware.
        text = str(exc)
        fallback = {"limit": limit, "timeout": 12}
        if required_domain and "required_domain" not in text:
            fallback["required_domain"] = required_domain
        try:
            urls = search_web_query(identity, query, **fallback)
        except TypeError:
            urls = search_web_query(identity, query, limit=limit, timeout=12)
    except Exception:
        urls = []
    metrics.setdefault("query", query)
    metrics.setdefault("raw_results", len(urls))
    metrics.setdefault("domain_results", len(urls))
    metrics.setdefault("valid_results", len(urls))
    return urls, metrics


def _emit_query_gain(callback, *, lane: str, query: str, signal_type: str, metrics: dict, before: set[str], after: set[str], stop_reason: str, domain: str | None = None) -> None:
    if callback is None:
        return
    new_urls = after - before
    callback({
        "lane": lane,
        "domain": domain,
        "query": query,
        "signal_type": signal_type,
        "raw_results": int(metrics.get("raw_results") or 0),
        "valid_results": int(metrics.get("valid_results") or 0),
        "new_urls": len(new_urls),
        "new_domains": len({_host(url) for url in new_urls if _host(url)}),
        "new_pdps": len(new_urls),
        "new_listings": len(new_urls),
        "new_sellers": 0,
        "stop_reason": stop_reason,
    })


def _discover_target_domain(identity: ProductIdentity, domain: str, limit_per_domain: int, on_query_event=None) -> list[str]:
    strong = _strong(identity)
    model = str(identity.model or identity.product_name or "").strip()
    alias_identity = _alias_identity(identity)
    found: list[str] = []
    seen: set[str] = set()
    for seed in _deterministic_pdps(identity):
        if _host_matches(seed, domain) and _is_pdp(seed, domain, strong):
            seen.add(seed)
            found.append(seed)
    signal_map = {query: signal for query, signal in _query_specs(identity, domain)}
    specs = [(query, signal_map.get(query, "UNKNOWN_SIGNAL")) for query in _queries(identity, domain)]
    for index, (query, signal_type) in enumerate(specs):
        before = set(seen)
        urls, metrics = _search_with_metrics(identity, query, limit=limit_per_domain, required_domain=domain)
        for raw in urls:
            url = str(raw or "").strip()
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            if not _host_matches(url, domain) or not _is_pdp(url, domain, strong):
                continue
            seen.add(url)
            found.append(url)
            if len(found) >= limit_per_domain:
                break
        if len(found) >= limit_per_domain:
            reason = "DOMAIN_LIMIT_REACHED"
        elif index == len(specs) - 1:
            reason = "QUERY_PLAN_EXHAUSTED"
        elif seen - before:
            reason = "CONTINUE_NOVELTY"
        else:
            reason = "CONTINUE_NO_NOVELTY"
        _emit_query_gain(on_query_event, lane="directed", query=query, signal_type=signal_type, metrics=metrics, before=before, after=set(seen), stop_reason=reason, domain=domain)
        if len(found) >= limit_per_domain:
            break
    if not found and model:
        alias_specs = [(query, "MODEL_ALIAS_FALLBACK") for query in _alias_queries(identity, domain)]
        for index, (query, signal_type) in enumerate(alias_specs):
            before = set(seen)
            urls, metrics = _search_with_metrics(alias_identity, query, limit=limit_per_domain, required_domain=domain)
            for raw in urls:
                url = str(raw or "").strip()
                if not url.startswith(("http://", "https://")) or url in seen:
                    continue
                if not _host_matches(url, domain) or not _is_pdp(url, domain, model):
                    continue
                seen.add(url)
                found.append(url)
                if len(found) >= limit_per_domain:
                    break
            reason = "DOMAIN_LIMIT_REACHED" if len(found) >= limit_per_domain else ("ALIAS_PLAN_EXHAUSTED" if index == len(alias_specs) - 1 else ("CONTINUE_NOVELTY" if seen - before else "CONTINUE_NO_NOVELTY"))
            _emit_query_gain(on_query_event, lane="directed_alias_fallback", query=query, signal_type=signal_type, metrics=metrics, before=before, after=set(seen), stop_reason=reason, domain=domain)
            if len(found) >= limit_per_domain:
                break
    return found


def discover_additional_peru_pdps(identity: ProductIdentity, *, limit_per_domain: int = 10, domains: tuple[str, ...] = PERU_MARKETPLACE_DOMAINS, on_query_event=None) -> list[str]:
    strong = _strong(identity)
    if not strong or not domains:
        return []
    workers = max(1, min(TARGET_DISCOVERY_WORKERS, len(domains)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="peru-channel") as pool:
        per_domain = list(pool.map(lambda domain: _discover_target_domain(identity, domain, limit_per_domain, on_query_event=on_query_event), domains))
    merged, seen_all = [], set()
    for index in range(limit_per_domain):
        for rows in per_domain:
            if index < len(rows) and rows[index] not in seen_all:
                seen_all.add(rows[index])
                merged.append(rows[index])
    return merged


def _is_peru_retail_candidate(url: str, strong: str, *, priority_domains: tuple[str, ...] = ()) -> bool:
    path, host = (urlparse(url).path or "").lower(), _host(url)
    if not host or any(marker in path for marker in _LISTING_MARKERS): return False
    if any(_host_matches(url, domain) for domain in PERU_MARKETPLACE_DOMAINS): return False
    local = host.endswith(".pe") or host.endswith(".com.pe")
    hinted = any(_host_matches(url, domain) for domain in (*PERU_RETAIL_HINT_DOMAINS, *priority_domains))
    peru_path = path.startswith("/peru")
    if not (local or hinted or peru_path): return False
    return bool((_compact(strong) and _compact(strong) in _compact(url)) or any(marker in path for marker in _PRODUCT_MARKERS))


def _general_retail_query_specs(identity: ProductIdentity, *, priority_domains: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    plan = build_price_query_plan(identity, limit=8)
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    specs: list[tuple[str, str]] = []
    for row in plan:
        signal = row.query
        specs += [
            (f'"{signal}" precio Perú', row.signal_type),
            (f'"{signal}" "S/" Perú', row.signal_type),
            (f'"{signal}" tienda Perú', row.signal_type),
        ]
    strong = _strong(identity)
    if strong and model:
        specs += [
            (f'"{strong}" "{model}" Perú', "MPN_MODEL"),
            (f'"{model}" "{strong}" {brand} Perú'.strip(), "BRAND_MODEL"),
        ]
    if strong:
        # Country-scope discovery finds Peru retailers that are not yet known to
        # capability memory or the static hint set. These are search-engine scopes,
        # not one literal hostname, so admission remains identity + Peru constrained.
        specs += [
            (f'"{strong}" site:.pe', "PERU_TLD_SCOPE"),
            (f'"{strong}" site:.com.pe', "PERU_TLD_SCOPE"),
        ]
        # Price receives identity.brand only after the upstream identity bridge has
        # accepted an explicit valid brand or an evidence-backed resolved brand.
        # Add exactly two country-scope representations for the canonical MPN;
        # do not expand punctuation aliases or invent a brand when MPN is absent.
        canonical_mpn = str(identity.mpn or "").strip()
        if brand and canonical_mpn:
            specs += [
                (f'"{brand}" "{canonical_mpn}" site:.pe', "VERIFIED_BRAND_MPN_PERU_TLD_SCOPE"),
                (f'"{brand}" "{canonical_mpn}" site:.com.pe', "VERIFIED_BRAND_MPN_PERU_TLD_SCOPE"),
            ]
        learned = tuple(dict.fromkeys(str(domain or "").strip().casefold().removeprefix("www.") for domain in priority_domains if str(domain or "").strip()))[:12]
        # Reuse the same bounded MPN alias family that the directed lane already
        # trusts. This prevents exact-separator indexing differences from hiding
        # a PDP inside a domain we already know, without expanding the source oracle.
        domain_signals = [row for row in plan if str(row.signal_type).startswith("MPN_")][:3]
        if not domain_signals:
            domain_signals = list(plan[:1])
        for domain in learned:
            for index, row in enumerate(domain_signals):
                signal_type = "LEARNED_DOMAIN" if index == 0 else f"LEARNED_DOMAIN_{row.signal_type}"
                specs.append((f'"{row.query}" site:{domain}', signal_type))
        for domain in PERU_RETAIL_HINT_DOMAINS:
            for index, row in enumerate(domain_signals):
                signal_type = "KNOWN_DOMAIN_HINT" if index == 0 else f"KNOWN_DOMAIN_HINT_{row.signal_type}"
                specs.append((f'"{row.query}" site:{domain}', signal_type))
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for query, signal_type in specs:
        clean = query.strip()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            out.append((clean, signal_type))
    return out


def _general_retail_queries(identity: ProductIdentity, *, priority_domains: tuple[str, ...] = ()) -> list[str]:
    return [query for query, _signal in _general_retail_query_specs(identity, priority_domains=priority_domains)]


def _general_alias_queries(identity: ProductIdentity) -> list[str]:
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    if not model:
        return []
    queries = [f'"{model}" "{brand}" precio Perú'.strip(), f'"{model}" "{brand}" tienda Perú'.strip()]
    queries += [f'"{model}" "{brand}" site:{domain}'.strip() for domain in PERU_RETAIL_HINT_DOMAINS]
    return list(dict.fromkeys(queries))


def _required_domain_from_query(query: str) -> str | None:
    match = re.search(r"(?:^|\s)site:([a-z0-9.-]+)", str(query or ""), flags=re.IGNORECASE)
    if not match:
        return None
    domain = match.group(1).casefold().removeprefix("www.")
    # site:.pe / site:.com.pe are country-wide search scopes, not literal hosts.
    if domain.startswith("."):
        return None
    return domain


def _country_scope_diversity_query(strong: str, seen_domains: set[str], *, round_index: int) -> str:
    scope = ".pe" if round_index % 2 == 0 else ".com.pe"
    domains = sorted({str(domain or "").strip().casefold().removeprefix("www.") for domain in seen_domains if str(domain or "").strip()})[:8]
    exclusions = " ".join(f"-site:{domain}" for domain in domains)
    return f'"{strong}" site:{scope} {exclusions}'.strip()


def _search_query_batches(identity: ProductIdentity, queries: list[str], per_query: int) -> list[list[str]]:
    if not queries:
        return []
    workers = max(1, min(RETAIL_QUERY_WORKERS, len(queries)))
    def run(query: str) -> list[str]:
        urls, _metrics = _search_with_metrics(
            identity, query, limit=per_query, required_domain=_required_domain_from_query(query)
        )
        return urls
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="peru-retail") as pool:
        return list(pool.map(run, queries))


def _search_query_specs(identity: ProductIdentity, specs: list[tuple[str, str]], per_query: int) -> list[tuple[str, str, list[str], dict]]:
    if not specs:
        return []
    workers = max(1, min(RETAIL_QUERY_WORKERS, len(specs)))
    def run(spec: tuple[str, str]):
        query, signal_type = spec
        urls, metrics = _search_with_metrics(
            identity, query, limit=per_query, required_domain=_required_domain_from_query(query)
        )
        return query, signal_type, urls, metrics
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="peru-retail-metrics") as pool:
        return list(pool.map(run, specs))


def _append_retail_candidates(rows: list[str], seen: set[str], batches: list[list[str]], marker: str, limit: int, *, priority_domains: tuple[str, ...] = ()) -> bool:
    for found in batches:
        for raw in found:
            url = str(raw or "").strip()
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            if not _is_peru_retail_candidate(url, marker, priority_domains=priority_domains):
                continue
            seen.add(url)
            rows.append(url)
            if len(rows) >= limit:
                return True
    return False


def discover_general_peru_retailers(identity: ProductIdentity, *, limit: int = 20, priority_domains: tuple[str, ...] = (), on_query_event=None) -> list[str]:
    strong = _strong(identity)
    if not strong or limit <= 0:
        return []
    rows: list[str] = []
    seen: set[str] = set()
    per_query = max(6, min(20, limit * 2))

    if on_query_event is None:
        exact_batches = _search_query_batches(identity, _general_retail_queries(identity, priority_domains=priority_domains), per_query)
        if _append_retail_candidates(rows, seen, exact_batches, strong, limit, priority_domains=priority_domains):
            return rows
    else:
        specs = _general_retail_query_specs(identity, priority_domains=priority_domains)
        batches = _search_query_specs(identity, specs, per_query)
        for index, (query, signal_type, found, metrics) in enumerate(batches):
            before = set(seen)
            for raw in found:
                url = str(raw or "").strip()
                if not url.startswith(("http://", "https://")) or url in seen:
                    continue
                if not _is_peru_retail_candidate(url, strong, priority_domains=priority_domains):
                    continue
                seen.add(url)
                rows.append(url)
                if len(rows) >= limit:
                    break
            reason = "RETAIL_LIMIT_REACHED" if len(rows) >= limit else ("QUERY_PLAN_EXHAUSTED" if index == len(batches) - 1 else ("CONTINUE_NOVELTY" if seen - before else "CONTINUE_NO_NOVELTY"))
            _emit_query_gain(on_query_event, lane="open_peru", query=query, signal_type=signal_type, metrics=metrics, before=before, after=set(seen), stop_reason=reason)
            if len(rows) >= limit:
                return rows

    # Search engines often keep returning the same high-ranked Peru retailers.
    # Use bounded negative-site expansion only after at least one valid retailer
    # was found; this surfaces new domains without hardcoding an oracle/source list.
    if rows and len(rows) < limit:
        no_novelty_rounds = 0
        for round_index in range(4):
            before = set(seen)
            seen_domains = {_host(url) for url in seen if _host(url)}
            query = _country_scope_diversity_query(strong, seen_domains, round_index=round_index)
            found, metrics = _search_with_metrics(identity, query, limit=per_query)
            for raw in found:
                url = str(raw or "").strip()
                if not url.startswith(("http://", "https://")) or url in seen:
                    continue
                if not _is_peru_retail_candidate(url, strong, priority_domains=priority_domains):
                    continue
                seen.add(url)
                rows.append(url)
                if len(rows) >= limit:
                    break
            gained = bool(seen - before)
            no_novelty_rounds = 0 if gained else no_novelty_rounds + 1
            if len(rows) >= limit:
                reason = "RETAIL_LIMIT_REACHED"
            elif no_novelty_rounds >= 2:
                reason = "DIVERSITY_NO_NOVELTY_STOP"
            elif gained:
                reason = "CONTINUE_NOVELTY"
            else:
                reason = "CONTINUE_NO_NOVELTY"
            _emit_query_gain(
                on_query_event,
                lane="open_peru_diversity",
                query=query,
                signal_type="PERU_TLD_DIVERSITY",
                metrics=metrics,
                before=before,
                after=set(seen),
                stop_reason=reason,
            )
            if len(rows) >= limit or no_novelty_rounds >= 2:
                break

    model = str(identity.model or identity.product_name or "").strip()
    if model and len(rows) < limit:
        alias_identity = _alias_identity(identity)
        alias_queries = _general_alias_queries(identity)
        if on_query_event is None:
            alias_batches = _search_query_batches(alias_identity, alias_queries, per_query)
            _append_retail_candidates(rows, seen, alias_batches, model, limit, priority_domains=priority_domains)
        else:
            alias_specs = [(query, "MODEL_ALIAS_FALLBACK") for query in alias_queries]
            for index, (query, signal_type, found, metrics) in enumerate(_search_query_specs(alias_identity, alias_specs, per_query)):
                before = set(seen)
                for raw in found:
                    url = str(raw or "").strip()
                    if not url.startswith(("http://", "https://")) or url in seen:
                        continue
                    if not _is_peru_retail_candidate(url, model, priority_domains=priority_domains):
                        continue
                    seen.add(url)
                    rows.append(url)
                    if len(rows) >= limit:
                        break
                reason = "RETAIL_LIMIT_REACHED" if len(rows) >= limit else ("ALIAS_PLAN_EXHAUSTED" if index == len(alias_specs) - 1 else ("CONTINUE_NOVELTY" if seen - before else "CONTINUE_NO_NOVELTY"))
                _emit_query_gain(on_query_event, lane="open_peru_alias_fallback", query=query, signal_type=signal_type, metrics=metrics, before=before, after=set(seen), stop_reason=reason)
                if len(rows) >= limit:
                    break
    return rows
