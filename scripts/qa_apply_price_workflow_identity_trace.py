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


def replace_n(path: str, old: str, new: str, expected: int) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{path}: expected {expected} replacement targets, got {count}: {old!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# Preserve existing optimization: alias fallback is only needed if exact-plan queries
# found no PDP. P3 novelty continuation happens within the exact plan itself.
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    "    if len(found) < limit_per_domain and model:\n",
    "    if not found and model:\n",
)

replace_once(
    "src/product_intelligence/price_workflow.py",
    "from .price_identity import competitor_key, dedupe_offers, filter_market_outliers, is_peru_offer\n",
    "from .price_identity import competitor_key, dedupe_offers, filter_market_outliers, is_peru_offer\nfrom .price_identity_resolution import resolve_price_identity\nfrom .price_trace import PriceCoverageTrace\n",
)

replace_once(
    "src/product_intelligence/price_workflow.py",
    '''def _collect_web_offers(sources: list[str], identity: ProductIdentity, emit) -> list[PriceOffer]:
    rows: list[PriceOffer] = []
    emit("status", stage="validating", message=f"Revisando {len(sources)} publicaciones web de Perú")
    for pos, url in enumerate(sources, 1):
        channel = _channel_from_url(url)
        try:
            emit("page", url=url, channel=channel, position=pos, total=len(sources), status="fetching")
            html, page_rows = _parse_page_with_dynamic_retry(url, identity, channel, emit)
            rows.extend(_augment_page_rows(url, html, page_rows, identity, channel))
            emit("page", url=url, channel=channel, status="parsed", offers=len(page_rows))
        except Exception as exc:
            emit("page", url=url, channel=channel, status="error", error=f"{type(exc).__name__}: {exc}")
    return rows
''',
    '''def _collect_web_offers(sources: list[str], identity: ProductIdentity, emit, *, trace: PriceCoverageTrace | None = None) -> list[PriceOffer]:
    rows: list[PriceOffer] = []
    emit("status", stage="validating", message=f"Revisando {len(sources)} publicaciones web de Perú")
    for pos, url in enumerate(sources, 1):
        channel = _channel_from_url(url)
        if trace:
            trace.record(channel, "URL_DISCOVERED", url=url)
            trace.record(channel, "FETCH_STARTED", url=url)
        try:
            emit("page", url=url, channel=channel, position=pos, total=len(sources), status="fetching")
            html, page_rows = _parse_page_with_dynamic_retry(url, identity, channel, emit)
            augmented = _augment_page_rows(url, html, page_rows, identity, channel)
            rows.extend(augmented)
            if trace:
                trace.record(channel, "FETCH_OK", url=url)
                trace.record(channel, "PARSER_STARTED", url=url)
                if augmented:
                    trace.record(channel, "IDENTITY_ACCEPTED", url=url)
                else:
                    trace.record(channel, "PARSER_ZERO_OFFERS", url=url)
            emit("page", url=url, channel=channel, status="parsed", offers=len(augmented))
        except Exception as exc:
            if trace:
                if isinstance(exc, (requests.Timeout, TimeoutError)):
                    trace.record(channel, "FETCH_TIMEOUT", url=url, detail=type(exc).__name__)
                else:
                    trace.record(channel, "FETCH_BLOCKED", url=url, detail=type(exc).__name__)
            emit("page", url=url, channel=channel, status="error", error=f"{type(exc).__name__}: {exc}")
    return rows
''',
)

replace_once(
    "src/product_intelligence/price_workflow.py",
    '''    offers: list[PriceOffer] = []
    learned_sources = load_validated_source_urls(output_root, identity)
''',
    '''    resolution = resolve_price_identity(identity)
    working_identity = resolution.identity
    trace = PriceCoverageTrace()
    emit(
        "identity",
        input_identity=identity.model_dump(),
        resolved_identity=working_identity.model_dump(),
        resolution_status=resolution.status,
        resolution_confidence=resolution.confidence,
        resolution_reason=resolution.reason,
        evidence_backed=resolution.evidence_backed,
        official_domain_hint=resolution.official_domain_hint,
    )

    offers: list[PriceOffer] = []
    learned_sources = load_validated_source_urls(output_root, identity)
''',
)

replace_once(
    "src/product_intelligence/price_workflow.py",
    '''    for channel, base_url in PERU_STRUCTURED_SOURCES:
        try:
            rows = _try_vtex(base_url, identity, channel)
            offers.extend(rows)
            emit("source", channel=channel, status="ok", offers=len(rows), method="structured_direct")
        except Exception as exc:
            emit("source", channel=channel, status="error", error=f"structured: {type(exc).__name__}: {exc}")
''',
    '''    for channel, base_url in PERU_STRUCTURED_SOURCES:
        trace.record(channel, "FETCH_STARTED", url=base_url)
        try:
            rows = _try_vtex(base_url, working_identity, channel)
            offers.extend(rows)
            trace.record(channel, "FETCH_OK", url=base_url)
            if rows:
                trace.record(channel, "IDENTITY_ACCEPTED", url=base_url)
            else:
                trace.record(channel, "PARSER_ZERO_OFFERS", url=base_url)
            emit("source", channel=channel, status="ok", offers=len(rows), method="structured_direct")
        except Exception as exc:
            trace.record(channel, "FETCH_BLOCKED", url=base_url, detail=type(exc).__name__)
            emit("source", channel=channel, status="error", error=f"structured: {type(exc).__name__}: {exc}")
''',
)

replace_once(
    "src/product_intelligence/price_workflow.py",
    '''    try:
        ml = _try_mercadolibre(identity)
        offers.extend(ml)
        emit("source", channel="MercadoLibre", status="ok", offers=len(ml), method="mercadolibre_mpe")
    except Exception as exc:
        emit("source", channel="MercadoLibre", status="error", error=f"{type(exc).__name__}: {exc}")
''',
    '''    try:
        ml = _try_mercadolibre(working_identity)
        offers.extend(ml)
        if ml:
            trace.record("MercadoLibre", "IDENTITY_ACCEPTED")
        else:
            trace.record("MercadoLibre", "QUERY_EXECUTED_NO_RESULT")
        emit("source", channel="MercadoLibre", status="ok", offers=len(ml), method="mercadolibre_mpe")
    except Exception as exc:
        trace.record("MercadoLibre", "FETCH_BLOCKED", detail=type(exc).__name__)
        emit("source", channel="MercadoLibre", status="error", error=f"{type(exc).__name__}: {exc}")
''',
)

# Every discovery/fetch path uses the canonical working identity. Persistence remains
# keyed by the original input so repeated MPN-only runs can reuse learned PDPs.
replace_n("src/product_intelligence/price_workflow.py", "_refresh_learned_sources, learned_sources, identity, emit", "_refresh_learned_sources, learned_sources, working_identity, emit", 1)
replace_n("src/product_intelligence/price_workflow.py", "discover_general_peru_retailers,\n                identity,", "discover_general_peru_retailers,\n                working_identity,", 1)
replace_n("src/product_intelligence/price_workflow.py", "_collect_web_offers(fresh_retail[:max_sources], identity, emit)", "_collect_web_offers(fresh_retail[:max_sources], working_identity, emit, trace=trace)", 1)
replace_n("src/product_intelligence/price_workflow.py", "discover_additional_peru_pdps(identity,", "discover_additional_peru_pdps(working_identity,", 1)
replace_n("src/product_intelligence/price_workflow.py", "discover_general_peru_retailers(identity,", "discover_general_peru_retailers(working_identity,", 1)
replace_n("src/product_intelligence/price_workflow.py", "discover_price_sources(identity,", "discover_price_sources(working_identity,", 1)
replace_n("src/product_intelligence/price_workflow.py", "_collect_web_offers(sources, identity, emit)", "_collect_web_offers(sources, working_identity, emit, trace=trace)", 1)

replace_once(
    "src/product_intelligence/price_workflow.py",
    '''    deduped = dedupe_offers(offers)
    trusted = [row for row in deduped if _is_trusted_final_offer(row)]
    valid, rejected_outliers = filter_market_outliers(trusted)
    if rejected_outliers:
        emit("quality", rejected_outliers=len(rejected_outliers), prices=[r.selling_price for r in rejected_outliers])

    coverage = build_channel_coverage(valid)
''',
    '''    deduped = dedupe_offers(offers)
    trusted = [row for row in deduped if _is_trusted_final_offer(row)]
    trusted_ids = {id(row) for row in trusted}
    for row in deduped:
        if id(row) not in trusted_ids:
            trace.record(row.channel, "PRICE_REJECTED", url=row.url)
    valid, rejected_outliers = filter_market_outliers(trusted)
    for row in rejected_outliers:
        trace.record(row.channel, "PRICE_REJECTED", url=row.url, detail="MARKET_OUTLIER")
    if rejected_outliers:
        emit("quality", rejected_outliers=len(rejected_outliers), prices=[r.selling_price for r in rejected_outliers])
    for row in valid:
        unavailable = str(row.availability or "").casefold()
        if row.stock == 0 or "outofstock" in unavailable or unavailable == "unavailable":
            trace.record(row.channel, "OUT_OF_STOCK", url=row.url, stock=False, seller=row.seller_display_name)
        else:
            trace.record(row.channel, "OFFER_ACCEPTED", url=row.url, stock=row.stock, seller=row.seller_display_name)

    coverage = build_channel_coverage(valid, source_states=trace.source_states())
''',
)

replace_once(
    "src/product_intelligence/price_workflow.py",
    '        target_channels_found=sum(1 for row in coverage["channels"] if row["status"] == "FOUND"),',
    '        target_channels_found=sum(1 for row in coverage["channels"] if row.get("offers")),',
)

print("PRICE_WORKFLOW_IDENTITY_TRACE_PATCH=APPLIED")
