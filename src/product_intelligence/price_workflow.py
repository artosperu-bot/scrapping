from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests

from .identity_bootstrap import bootstrap_identity
from .mercadolibre_oauth import MercadoLibreAuthError, build_mercadolibre_api_client
from .models import ProductIdentity
from .price_adapters import parse_mercadolibre_payload, parse_shopify_product_payload, parse_vtex_payload
from .price_channel_registry import build_channel_coverage, target_spec_for_url
from .price_discovery import discover_price_sources, extract_page_offers
from .price_history import (
    load_validated_source_urls,
    save_channel_coverage,
    save_price_run,
    save_validated_source_bindings,
)
from .price_identity import competitor_key, dedupe_offers, filter_market_outliers, is_peru_offer
from .price_models import PriceOffer
from .price_peru_coverage import discover_additional_peru_pdps, discover_general_peru_retailers
from .price_source_capabilities import SourceCapabilityRegistry, detect_platform
from .price_trace import PriceTrace
from .web_fetch import fetch_page

PERU_STRUCTURED_SOURCES: tuple[tuple[str, str], ...] = (
    ("Falabella", "https://www.falabella.com.pe"),
    ("PlazaVea", "https://www.plazavea.com.pe"),
    ("Oechsle", "https://www.oechsle.pe"),
)

STRICT_MARKETPLACE_CHANNELS = {"falabella","ripley","plazavea","oechsle","mercadolibre","sodimac","jblperu"}
BROWSER_PRICE_CHANNELS = {"Ripley", "MercadoLibre", "Mercado Libre", "JBL Perú"}


class PriceFetchBlocked(RuntimeError):
    def __init__(self, status_code: int, url: str):
        self.status_code = int(status_code)
        self.url = str(url)
        super().__init__(f"HTTP {self.status_code}")


def _query(identity: ProductIdentity) -> str:
    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or "").strip()


def _resolve_price_identity(identity: ProductIdentity) -> tuple[ProductIdentity, dict]:
    if not _query(identity):
        return identity, {"status": "IDENTITY_UNRESOLVED", "confidence": 0.0, "reason": "NO_IDENTITY_SIGNAL", "official_domain_hint": None}
    if identity.brand and (identity.model or identity.product_name) and (identity.mpn or identity.ean or identity.upc or identity.gtin):
        return identity, {"status": "ALREADY_RESOLVED", "confidence": float(identity.confidence or 1.0), "reason": "INPUT_HAS_STRONG_IDENTITY", "official_domain_hint": None}
    try:
        result = bootstrap_identity(identity, limit_per_query=14, timeout=8)
    except Exception as exc:
        return identity, {"status": "IDENTITY_UNRESOLVED", "confidence": 0.0, "reason": f"BOOTSTRAP_ERROR:{type(exc).__name__}", "official_domain_hint": None}
    resolved = getattr(result, "identity", None) or identity
    status = str(getattr(result, "status", "IDENTITY_UNRESOLVED") or "IDENTITY_UNRESOLVED")
    if status != "RESOLVED":
        resolved = identity
    return resolved, {
        "status": status,
        "confidence": float(getattr(result, "confidence", 0.0) or 0.0),
        "reason": str(getattr(result, "reason", "") or ""),
        "official_domain_hint": getattr(result, "official_domain_hint", None),
    }


def _channel_from_url(url: str) -> str:
    target = target_spec_for_url(url)
    if target:
        return target.label
    host = (urlparse(url).hostname or "web").lower().removeprefix("www.")
    names = {
        "jbl":"JBL Perú","infiniti":"Infiniti","perudataconsult":"Peru Data","arteus":"Arteus",
        "baetech":"BaeTech","panacompu":"Pana Compu","memorykings":"Memory Kings","estuyo":"EsTuyo",
        "bigmarket":"Big Market",
    }
    for key, name in names.items():
        if key in host:
            return name
    return (host.split(".")[0] if host else "Web").replace("-", " ").title()


def _channel_key(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _is_trusted_final_offer(row: PriceOffer) -> bool:
    if not is_peru_offer(row) or row.confidence < 0.70 or row.selling_price <= 0:
        return False
    if _channel_key(row.channel) in STRICT_MARKETPLACE_CHANNELS and row.source_method == "html":
        return False
    return True


def _mercadolibre_queries(identity: ProductIdentity) -> list[str]:
    values = [
        _query(identity),
        " ".join(v for v in (identity.brand, identity.model or identity.product_name) if v).strip(),
        str(identity.model or identity.product_name or "").strip(),
    ]
    return list(dict.fromkeys(v for v in values if v))


def _try_mercadolibre(identity: ProductIdentity, timeout: int = 15) -> list[PriceOffer]:
    rows: list[PriceOffer] = []
    errors: list[Exception] = []
    queries = _mercadolibre_queries(identity)
    client = build_mercadolibre_api_client(timeout=timeout)
    for q in queries:
        try:
            url = f"https://api.mercadolibre.com/sites/MPE/search?q={quote_plus(q)}&limit=50"
            response = client.get(url, timeout=timeout)
            response.raise_for_status()
            rows.extend(parse_mercadolibre_payload(response.json(), identity))
        except Exception as exc:
            errors.append(exc)
    if rows:
        return dedupe_offers(rows)
    if errors and len(errors) == len(queries):
        raise errors[0]
    return []


def _try_vtex(url: str, identity: ProductIdentity, channel: str, timeout: int = 12) -> list[PriceOffer]:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    endpoint = f"{origin}/api/catalog_system/pub/products/search?ft={quote_plus(_query(identity))}&_from=0&_to=49"
    response = requests.get(endpoint, timeout=timeout, headers={"User-Agent": "ProductIntelligence/0.10"})
    if response.status_code != 200:
        return []
    data = response.json()
    if not isinstance(data, (list, dict)):
        return []
    return parse_vtex_payload(data, identity, channel=channel, source_url=origin)


def _try_shopify(url: str, identity: ProductIdentity, channel: str, timeout: int = 12) -> list[PriceOffer]:
    parsed = urlparse(url)
    path = (parsed.path or "").rstrip("/")
    if "/products/" not in path.lower():
        return []
    endpoint = f"{parsed.scheme}://{parsed.netloc}{path}.js"
    response = requests.get(endpoint, timeout=timeout, headers={"User-Agent": "ProductIntelligence/0.10"})
    if response.status_code != 200:
        return []
    try:
        data = response.json()
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    return parse_shopify_product_payload(data, identity, channel=channel, source_url=url)


def _best_by_currency(offers: list[PriceOffer]) -> dict[str, float]:
    best: dict[str, float] = {}
    for row in offers:
        currency = str(row.currency or "").upper() or "UNKNOWN"
        current = best.get(currency)
        if current is None or row.selling_price < current:
            best[currency] = row.selling_price
    return best


def _merge_sources(*groups: list[str], limit: int) -> list[str]:
    """Interleave source families so one marketplace cannot consume the fetch budget."""
    merged: list[str] = []
    seen: set[str] = set()
    max_len = max((len(group) for group in groups), default=0)
    for index in range(max_len):
        for group in groups:
            if index >= len(group):
                continue
            clean = str(group[index] or "").strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            merged.append(clean)
            if len(merged) >= limit:
                return merged
    return merged


def _parse_page_with_dynamic_retry(url: str, identity: ProductIdentity, channel: str, emit) -> tuple[str, list[PriceOffer]]:
    fetched = fetch_page(url, timeout=25, browser_fallback=True, activate_lazy_media=False)
    final_url = str(getattr(fetched, "final_url", None) or url)
    status_code = int(getattr(fetched, "status_code", 0) or 0)
    if status_code in {401, 403, 429}:
        raise PriceFetchBlocked(status_code, final_url)
    if status_code >= 400:
        raise requests.HTTPError(f"HTTP {status_code}")
    html = str(getattr(fetched, "html", "") or "")
    page_rows = extract_page_offers(html, final_url, identity, channel=channel)
    if not page_rows and channel in BROWSER_PRICE_CHANNELS and getattr(fetched, "method", "") != "playwright":
        try:
            rendered = fetch_page(url, timeout=35, browser_fallback=True, prefer_browser=True, activate_lazy_media=False)
            rendered_url = str(getattr(rendered, "final_url", None) or final_url)
            rendered_html = str(getattr(rendered, "html", "") or "")
            rendered_rows = extract_page_offers(rendered_html, rendered_url, identity, channel=channel)
            emit("page", url=rendered_url, channel=channel, status="browser_retry", offers=len(rendered_rows), method=getattr(rendered, "method", None))
            if rendered_rows:
                return rendered_html, rendered_rows
        except Exception as exc:
            emit("page", url=url, channel=channel, status="browser_error", error=f"{type(exc).__name__}: {exc}")
    return html, page_rows


def _augment_page_rows(url: str, html: str, page_rows: list[PriceOffer], identity: ProductIdentity, channel: str) -> list[PriceOffer]:
    rows = list(page_rows)
    lower = html.lower()
    if "vtex" in lower or "vteximg" in lower or "/api/catalog_system/" in lower:
        try:
            rows.extend(_try_vtex(url, identity, channel, timeout=8))
        except Exception:
            pass
    try:
        rows.extend(_try_shopify(url, identity, channel, timeout=8))
    except Exception:
        pass
    return rows


def _refresh_learned_static(url: str, identity: ProductIdentity) -> tuple[list[PriceOffer], bool]:
    channel = _channel_from_url(url)
    try:
        fetched = fetch_page(url, timeout=8, browser_fallback=False, activate_lazy_media=False)
        final_url = str(getattr(fetched, "final_url", None) or url)
        html = str(getattr(fetched, "html", "") or "")
        page_rows = extract_page_offers(html, final_url, identity, channel=channel)
        rows = _augment_page_rows(final_url, html, page_rows, identity, channel)
        trusted = [row for row in rows if _is_trusted_final_offer(row)]
        return rows, not bool(trusted)
    except Exception:
        return [], True


def _refresh_learned_sources(urls: list[str], identity: ProductIdentity, emit) -> list[PriceOffer]:
    """Re-fetch remembered PDPs. Static/API work may run concurrently; browser work never does."""
    unique_urls = list(dict.fromkeys(str(url or "").strip() for url in urls if str(url or "").strip()))
    if not unique_urls:
        return []

    rows: list[PriceOffer] = []
    unresolved: list[str] = []
    workers = min(8, len(unique_urls))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="price-learned") as pool:
        futures = {pool.submit(_refresh_learned_static, url, identity): url for url in unique_urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                found, needs_browser = future.result()
                rows.extend(found)
                if needs_browser:
                    unresolved.append(url)
            except Exception as exc:
                unresolved.append(url)
                emit("page", url=url, channel=_channel_from_url(url), status="error", error=f"learned_static: {type(exc).__name__}: {exc}")

    for url in unresolved:
        channel = _channel_from_url(url)
        try:
            html, page_rows = _parse_page_with_dynamic_retry(url, identity, channel, emit)
            rows.extend(_augment_page_rows(url, html, page_rows, identity, channel))
        except Exception as exc:
            emit("page", url=url, channel=channel, status="error", error=f"learned_browser: {type(exc).__name__}: {exc}")
    return dedupe_offers(rows)


def _collect_web_offers(sources: list[str], identity: ProductIdentity, emit, capabilities: SourceCapabilityRegistry | None = None) -> list[PriceOffer]:
    rows: list[PriceOffer] = []
    emit("status", stage="validating", message=f"Revisando {len(sources)} publicaciones web de Perú")
    for pos, url in enumerate(sources, 1):
        channel = _channel_from_url(url)
        try:
            emit("page", url=url, channel=channel, position=pos, total=len(sources), status="fetching")
            html, page_rows = _parse_page_with_dynamic_retry(url, identity, channel, emit)
            augmented = _augment_page_rows(url, html, page_rows, identity, channel)
            rows.extend(augmented)
            if capabilities is not None:
                method = next((row.source_method for row in augmented if row.source_method), None)
                capabilities.observe(
                    url,
                    platform=detect_platform(url, html),
                    discovery_method="price_discovery",
                    extraction_method=method,
                    price_capable=bool(augmented),
                    stock_capable=any(row.stock is not None or bool(row.availability) for row in augmented),
                    seller_capable=any(bool(row.seller_display_name or row.seller_legal_name) for row in augmented),
                    success=any(_is_trusted_final_offer(row) for row in augmented),
                )
            emit("page", url=url, channel=channel, status="parsed", offers=len(page_rows))
        except PriceFetchBlocked as exc:
            emit("page", url=url, channel=channel, status="blocked", http_status=exc.status_code, error=str(exc))
        except requests.Timeout as exc:
            emit("page", url=url, channel=channel, status="timeout", error=f"{type(exc).__name__}: {exc}")
        except Exception as exc:
            emit("page", url=url, channel=channel, status="error", error=f"{type(exc).__name__}: {exc}")
    return rows


def _has_trusted_offer(rows: list[PriceOffer]) -> bool:
    return any(_is_trusted_final_offer(row) for row in dedupe_offers(rows))


def run_price_product(identity: ProductIdentity, output_root: str | Path, *, on_event=None, max_sources: int = 48) -> list[PriceOffer]:
    input_identity = identity
    identity, identity_resolution = _resolve_price_identity(input_identity)
    trace = PriceTrace()
    capabilities = SourceCapabilityRegistry(Path(output_root) / "price_intelligence" / "source_capabilities.json")

    def discovery_event(event: dict) -> None:
        stage = str(event.get("stage") or "QUERY_EXECUTED")
        payload = {k: v for k, v in event.items() if k != "stage"}
        trace.record(stage, **payload)

    def emit(event_type: str, **payload):
        if event_type == "page":
            status = str(payload.get("status") or "").lower()
            channel = payload.get("channel")
            url = payload.get("url")
            if status == "fetching":
                trace.record("URL_DISCOVERED", channel=channel, url=url)
                trace.record("FETCH_STARTED", channel=channel, url=url)
            elif status == "parsed":
                trace.record("FETCH_OK", channel=channel, url=url)
                trace.record("PARSER_STARTED", channel=channel, url=url)
                if int(payload.get("offers") or 0) > 0:
                    trace.record("PARSER_OK", channel=channel, url=url, offers=int(payload.get("offers") or 0))
                else:
                    trace.record("PARSER_ZERO_OFFERS", channel=channel, url=url)
            elif status == "blocked":
                trace.record("FETCH_BLOCKED", channel=channel, url=url, http_status=payload.get("http_status"), error=payload.get("error"))
            elif status == "timeout":
                trace.record("FETCH_TIMEOUT", channel=channel, url=url, error=payload.get("error"))
            elif status in {"error", "browser_error"}:
                trace.record("FETCH_FAILED", channel=channel, url=url, error=payload.get("error"))
        if on_event:
            on_event({"type": event_type, "identity": identity.model_dump(), **payload})

    emit("identity", input_identity=input_identity.model_dump(), resolved_identity=identity.model_dump(), **identity_resolution)
    offers: list[PriceOffer] = []
    learned_sources = load_validated_source_urls(output_root, identity)
    warm_path = bool(learned_sources)
    emit("status", stage="searching", message="Consultando APIs y fuentes estructuradas de Perú")

    for channel, base_url in PERU_STRUCTURED_SOURCES:
        trace.record("QUERY_EXECUTED", channel=channel, query=_query(identity), method="structured_direct")
        try:
            rows = _try_vtex(base_url, identity, channel)
            offers.extend(rows)
            if rows:
                for row in rows:
                    trace.record("IDENTITY_ACCEPTED", channel=channel, url=row.url, identity_match=row.identity_match)
                    trace.record("PRICE_EXTRACTED", channel=channel, url=row.url, price=row.selling_price, currency=row.currency)
            else:
                trace.record("QUERY_EXECUTED_NO_RESULT", channel=channel, query=_query(identity), method="structured_direct")
            emit("source", channel=channel, status="ok", offers=len(rows), method="structured_direct")
        except Exception as exc:
            emit("source", channel=channel, status="error", error=f"structured: {type(exc).__name__}: {exc}")

    trace.record("QUERY_EXECUTED", channel="Mercado Libre", query=_query(identity), method="mercadolibre_mpe")
    try:
        ml = _try_mercadolibre(identity)
        offers.extend(ml)
        if ml:
            for row in ml:
                trace.record("IDENTITY_ACCEPTED", channel="Mercado Libre", url=row.url, identity_match=row.identity_match)
                trace.record("PRICE_EXTRACTED", channel="Mercado Libre", url=row.url, price=row.selling_price, currency=row.currency)
        else:
            trace.record("QUERY_EXECUTED_NO_RESULT", channel="Mercado Libre", query=_query(identity), method="mercadolibre_mpe")
        emit("source", channel="MercadoLibre", status="ok", offers=len(ml), method="mercadolibre_mpe")
    except MercadoLibreAuthError as exc:
        trace.record("ML_API_AUTH_FAILED", channel="Mercado Libre", code=exc.code, http_status=exc.http_status)
        emit("source", channel="MercadoLibre", status="auth_failed", error_code=exc.code)
    except Exception as exc:
        emit("source", channel="MercadoLibre", status="error", error=f"{type(exc).__name__}: {exc}")

    retail_sources: list[str] = []
    if warm_path:
        emit("source", channel="learned", status="refreshing", urls=len(learned_sources), method="validated_source_memory")
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="price-warm") as pool:
            learned_future = pool.submit(_refresh_learned_sources, learned_sources, identity, emit)
            retail_future = pool.submit(
                discover_general_peru_retailers,
                identity,
                limit=max(10, max_sources // 2),
                on_event=discovery_event,
            )
            try:
                learned_rows = learned_future.result()
            except Exception as exc:
                learned_rows = []
                emit("source", channel="learned", status="error", error=f"refresh: {type(exc).__name__}: {exc}")
            try:
                retail_sources = retail_future.result()
            except Exception as exc:
                retail_sources = []
                emit("source", channel="peru_retail", status="error", error=f"discovery: {type(exc).__name__}: {exc}")
        offers.extend(learned_rows)
        emit("source", channel="learned", status="ok", offers=len(learned_rows), urls=len(learned_sources), method="validated_source_memory")
        emit("source", channel="peru_retail", status="ok", offers=0, urls=len(retail_sources), method="identifier_and_alias_retail")
        learned_set = set(learned_sources)
        fresh_retail = [url for url in retail_sources if url not in learned_set]
        offers.extend(_collect_web_offers(fresh_retail[:max_sources], identity, emit, capabilities))

    marketplace_sources: list[str] = []
    base_sources: list[str] = []
    if not warm_path or not _has_trusted_offer(offers):
        try:
            marketplace_sources = discover_additional_peru_pdps(identity, limit_per_domain=max(4, min(10, max_sources // 4 or 4)), on_event=discovery_event)
            for url in marketplace_sources:
                trace.record("URL_DISCOVERED", channel=_channel_from_url(url), url=url, method="targeted_pdp")
            emit("source", channel="peru_directed", status="ok", offers=0, urls=len(marketplace_sources), method="targeted_pdp")
        except Exception as exc:
            emit("source", channel="peru_directed", status="error", error=f"discovery: {type(exc).__name__}: {exc}")
        if not warm_path:
            try:
                retail_sources = discover_general_peru_retailers(identity, limit=max(10, max_sources // 2), on_event=discovery_event)
                for url in retail_sources:
                    trace.record("URL_DISCOVERED", channel=_channel_from_url(url), url=url, method="identifier_and_alias_retail")
                emit("source", channel="peru_retail", status="ok", offers=0, urls=len(retail_sources), method="identifier_and_alias_retail")
            except Exception as exc:
                emit("source", channel="peru_retail", status="error", error=f"discovery: {type(exc).__name__}: {exc}")
        try:
            base_sources = discover_price_sources(identity, limit=max_sources, allow_identity_bootstrap=False)
            for url in base_sources:
                trace.record("URL_DISCOVERED", channel=_channel_from_url(url), url=url, method="generic_peru")
            emit("source", channel="web", status="ok", offers=0, urls=len(base_sources), method="generic_peru")
        except Exception as exc:
            emit("source", channel="web", status="error", error=f"discovery: {type(exc).__name__}: {exc}")

        skip_urls = set(learned_sources) if warm_path else set()
        sources = [
            url
            for url in _merge_sources(marketplace_sources, retail_sources, base_sources, limit=max_sources)
            if url not in skip_urls
        ]
        offers.extend(_collect_web_offers(sources, identity, emit, capabilities))

    deduped = dedupe_offers(offers)
    trusted = [row for row in deduped if _is_trusted_final_offer(row)]
    valid, rejected_outliers = filter_market_outliers(trusted)
    if rejected_outliers:
        emit("quality", rejected_outliers=len(rejected_outliers), prices=[r.selling_price for r in rejected_outliers])

    for row in valid:
        trace.record("OFFER_ACCEPTED", channel=row.channel, url=row.url, price=row.selling_price, currency=row.currency, seller=row.seller_display_name, identity_match=row.identity_match)
    coverage = trace.coverage(valid)
    emit("status", stage="saving", message=f"Guardando {len(valid)} ofertas peruanas validadas")
    save_price_run(output_root, valid)
    save_validated_source_bindings(output_root, identity, valid)
    save_channel_coverage(output_root, coverage)
    capabilities.save()
    emit("coverage", report=coverage)
    for row in valid:
        emit("offer", offer=row.to_dict())
    emit(
        "done",
        offers=len(valid),
        channels=len({r.channel for r in valid}),
        sellers=len({competitor_key(r) for r in valid}),
        target_channels_found=sum(1 for row in coverage["channels"] if row.get("final_status") in {"OFFER_ACCEPTED", "OUT_OF_STOCK"}),
        individual_stores=coverage["individual_store_count"],
        best_by_currency=_best_by_currency(valid),
    )
    return valid
