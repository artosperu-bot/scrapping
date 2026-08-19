from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def replace_section(path: str, start: str, end: str, replacement: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1:
        raise SystemExit(f"{path}: ambiguous section markers {start!r} / {end!r}")
    left = text.index(start)
    right = text.index(end, left)
    target.write_text(text[:left] + replacement + text[right:], encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected exactly one target, got {text.count(old)}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# P3/P6 observability — expose raw/domain/valid query counts without changing ranking.
replace_section(
    "src/product_intelligence/discovery.py",
    "def _budgeted_query(",
    "def _bootstrap_unknown_identity(",
    '''def _budgeted_query(identity:ProductIdentity,query:str,timeout:int,tracker:SearchBudgetTracker,required_domain:str|None=None,on_metrics=None)->list[SearchCandidate]:
    if not query or not tracker.reserve_query():
        if on_metrics:
            on_metrics({"query":str(query or "").strip(),"raw_results":0,"domain_results":0,"valid_results":0})
        return []
    raw_rows=_provider_search(query,timeout)
    domain_rows=_provider_rows_for_domain(raw_rows,required_domain)
    ranked=_rank_candidates(domain_rows,identity,tracker.budget.max_candidates_per_query)
    tracker.admit_candidates(len(ranked))
    if on_metrics:
        on_metrics({"query":query,"raw_results":len(raw_rows),"domain_results":len(domain_rows),"valid_results":len(ranked)})
    return ranked


def search_web_query(identity:ProductIdentity,query:str,limit:int=6,timeout:int=8,budget_tracker:SearchBudgetTracker|None=None,required_domain:str|None=None,on_metrics=None)->list[str]:
    clean=str(query or "").strip()
    if not clean:
        if on_metrics:on_metrics({"query":"","raw_results":0,"domain_results":0,"valid_results":0})
        return []
    if budget_tracker is not None:
        ranked=_budgeted_query(identity,clean,timeout,budget_tracker,required_domain=required_domain,on_metrics=on_metrics)
        return [row.url for row in ranked[:limit]]
    raw_rows=_provider_search(clean,timeout)
    domain_rows=_provider_rows_for_domain(raw_rows,required_domain)
    ranked=_rank_candidates(domain_rows,identity,max(limit*2,limit))
    visible=ranked[:limit]
    if on_metrics:
        on_metrics({"query":clean,"raw_results":len(raw_rows),"domain_results":len(domain_rows),"valid_results":len(visible)})
    return [row.url for row in visible]


''',
)

# Directed/open Peru query novelty ledger. Keep the old emergency model alias lane,
# but primary MPN separator aliases continue until budget/plan exhaustion.
replace_section(
    "src/product_intelligence/price_peru_coverage.py",
    "def _queries(",
    "def _alias_queries(",
    '''def _query_specs(identity: ProductIdentity, domain: str) -> list[tuple[str, str]]:
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


''',
)

replace_section(
    "src/product_intelligence/price_peru_coverage.py",
    "def _discover_target_domain(",
    "def discover_additional_peru_pdps(",
    '''def _search_with_metrics(identity: ProductIdentity, query: str, *, limit: int, required_domain: str | None = None) -> tuple[list[str], dict]:
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
    specs = _query_specs(identity, domain)
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


''',
)

replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    "def discover_additional_peru_pdps(identity: ProductIdentity, *, limit_per_domain: int = 10, domains: tuple[str, ...] = PERU_MARKETPLACE_DOMAINS) -> list[str]:",
    "def discover_additional_peru_pdps(identity: ProductIdentity, *, limit_per_domain: int = 10, domains: tuple[str, ...] = PERU_MARKETPLACE_DOMAINS, on_query_event=None) -> list[str]:",
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    "per_domain = list(pool.map(lambda domain: _discover_target_domain(identity, domain, limit_per_domain), domains))",
    "per_domain = list(pool.map(lambda domain: _discover_target_domain(identity, domain, limit_per_domain, on_query_event=on_query_event), domains))",
)

replace_section(
    "src/product_intelligence/price_peru_coverage.py",
    "def _general_retail_queries(",
    "def _general_alias_queries(",
    '''def _general_retail_query_specs(identity: ProductIdentity, *, priority_domains: tuple[str, ...] = ()) -> list[tuple[str, str]]:
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
        learned = tuple(dict.fromkeys(str(domain or "").strip().casefold().removeprefix("www.") for domain in priority_domains if str(domain or "").strip()))[:12]
        specs += [(f'"{strong}" site:{domain}', "LEARNED_DOMAIN") for domain in learned]
        specs += [(f'"{strong}" site:{domain}', "KNOWN_DOMAIN_HINT") for domain in PERU_RETAIL_HINT_DOMAINS]
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


''',
)

replace_section(
    "src/product_intelligence/price_peru_coverage.py",
    "def _search_query_batches(",
    "def _append_retail_candidates(",
    '''def _search_query_batches(identity: ProductIdentity, queries: list[str], per_query: int) -> list[list[str]]:
    if not queries:
        return []
    workers = max(1, min(RETAIL_QUERY_WORKERS, len(queries)))
    def run(query: str) -> list[str]:
        try:
            return search_web_query(identity, query, limit=per_query, timeout=12)
        except Exception:
            return []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="peru-retail") as pool:
        return list(pool.map(run, queries))


def _search_query_specs(identity: ProductIdentity, specs: list[tuple[str, str]], per_query: int) -> list[tuple[str, str, list[str], dict]]:
    if not specs:
        return []
    workers = max(1, min(RETAIL_QUERY_WORKERS, len(specs)))
    def run(spec: tuple[str, str]):
        query, signal_type = spec
        urls, metrics = _search_with_metrics(identity, query, limit=per_query)
        return query, signal_type, urls, metrics
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="peru-retail-metrics") as pool:
        return list(pool.map(run, specs))


''',
)

replace_section(
    "src/product_intelligence/price_peru_coverage.py",
    "def discover_general_peru_retailers(",
    "return rows",
    '''def discover_general_peru_retailers(identity: ProductIdentity, *, limit: int = 20, priority_domains: tuple[str, ...] = (), on_query_event=None) -> list[str]:
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
    return rows''',
)

# Mercado Libre query-level listing/seller novelty and live forwarding into the run ledger.
replace_section(
    "src/product_intelligence/price_workflow.py",
    "def _try_mercadolibre(",
    "def _try_vtex(",
    '''def _try_mercadolibre(identity: ProductIdentity, timeout: int = 15, on_query_event=None) -> list[PriceOffer]:
    rows: list[PriceOffer] = []
    errors: list[Exception] = []
    queries = _mercadolibre_queries(identity)
    signal_map = {row.query: row.signal_type for row in build_price_query_plan(identity, limit=12)}
    client = build_mercadolibre_api_client(timeout=timeout)
    seen_listings: set[str] = set()
    seen_sellers: set[str] = set()
    seen_domains: set[str] = set()
    for index, q in enumerate(queries):
        raw_count = 0
        parsed_rows: list[PriceOffer] = []
        before_listings = set(seen_listings)
        before_sellers = set(seen_sellers)
        before_domains = set(seen_domains)
        try:
            url = f"https://api.mercadolibre.com/sites/MPE/search?q={quote_plus(q)}&limit=50"
            response = client.get(url, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            raw_results = payload.get("results") if isinstance(payload, dict) else []
            raw_count = len(raw_results) if isinstance(raw_results, list) else 0
            parsed_rows = parse_mercadolibre_payload(payload, identity)
            rows.extend(parsed_rows)
            for row in parsed_rows:
                listing = str(row.publication_id or row.url or "").strip()
                seller = str(row.seller_tax_id or row.seller_legal_name or row.seller_display_name or "").strip().casefold()
                host = (urlparse(row.url).hostname or "").casefold().removeprefix("www.")
                if listing: seen_listings.add(listing)
                if seller: seen_sellers.add(seller)
                if host: seen_domains.add(host)
        except Exception as exc:
            errors.append(exc)
        if on_query_event:
            new_listings = seen_listings - before_listings
            new_sellers = seen_sellers - before_sellers
            if index == len(queries) - 1:
                reason = "QUERY_PLAN_EXHAUSTED"
            elif new_listings or new_sellers:
                reason = "CONTINUE_NOVELTY"
            else:
                reason = "CONTINUE_NO_NOVELTY"
            on_query_event({
                "lane": "mercadolibre_api",
                "domain": "mercadolibre.com.pe",
                "query": q,
                "signal_type": signal_map.get(q, "UNKNOWN_SIGNAL"),
                "raw_results": raw_count,
                "valid_results": len(parsed_rows),
                "new_urls": len(new_listings),
                "new_domains": len(seen_domains - before_domains),
                "new_pdps": len(new_listings),
                "new_listings": len(new_listings),
                "new_sellers": len(new_sellers),
                "stop_reason": reason,
            })
    if rows:
        return dedupe_offers(rows)
    if errors and len(errors) == len(queries):
        raise errors[0]
    return []


''',
)

replace_once(
    "src/product_intelligence/price_workflow.py",
    '''    def emit(event_type: str, **payload):
        if on_event:
            on_event({"type": event_type, "identity": identity.model_dump(), **payload})

    resolution = resolve_price_identity(identity)
''',
    '''    def emit(event_type: str, **payload):
        if on_event:
            on_event({"type": event_type, "identity": identity.model_dump(), **payload})

    def emit_query(payload: dict):
        emit("query", **payload)

    resolution = resolve_price_identity(identity)
''',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '''        official_domain_hint=resolution.official_domain_hint,
    )
''',
    '''        official_domain_hint=resolution.official_domain_hint,
        candidate_urls=list(resolution.candidate_urls),
        page_signals=list(resolution.page_signals),
    )
''',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "ml = _try_mercadolibre(working_identity)",
    "ml = _try_mercadolibre(working_identity, on_query_event=emit_query)",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '''                priority_domains=priority_domains,
            )
''',
    '''                priority_domains=priority_domains,
                on_query_event=emit_query,
            )
''',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "marketplace_sources = discover_additional_peru_pdps(working_identity, limit_per_domain=max(4, min(10, max_sources // 4 or 4)))",
    "marketplace_sources = discover_additional_peru_pdps(working_identity, limit_per_domain=max(4, min(10, max_sources // 4 or 4)), on_query_event=emit_query)",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '''                    working_identity, limit=max(10, max_sources // 2), priority_domains=priority_domains,
                )
''',
    '''                    working_identity, limit=max(10, max_sources // 2), priority_domains=priority_domains,
                    on_query_event=emit_query,
                )
''',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '''        best_by_currency=_best_by_currency(valid),
    )
''',
    '''        best_by_currency=_best_by_currency(valid),
        candidate_offers=len(offers),
        deduped_offers=len(deduped),
        duplicates=max(0, len(offers) - len(deduped)),
        trusted_offers=len(trusted),
        price_rejected=max(0, len(deduped) - len(trusted)) + len(rejected_outliers),
    )
''',
)

print("PRICE_QUERY_TELEMETRY_PATCH=APPLIED")
