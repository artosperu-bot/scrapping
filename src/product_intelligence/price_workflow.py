from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests

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
from .price_identity_resolution import resolve_price_identity
from .price_trace import PriceCoverageTrace
from .price_models import PriceOffer
from .price_queries import build_price_query_plan
from .price_peru_coverage import discover_additional_peru_pdps, discover_general_peru_retailers
from .price_source_capabilities import SourceCapabilityRegistry, detect_ecommerce_platform
from .product_classification import classify_product
from .web_fetch import fetch_page

PERU_STRUCTURED_SOURCES: tuple[tuple[str, str], ...] = (
    ("Falabella", "https://www.falabella.com.pe"),
    ("PlazaVea", "https://www.plazavea.com.pe"),
    ("Oechsle", "https://www.oechsle.pe"),
)

STRICT_MARKETPLACE_CHANNELS = {"falabella","ripley","plazavea","oechsle","mercadolibre","sodimac","jblperu"}
BROWSER_PRICE_CHANNELS = {"Ripley", "MercadoLibre", "Mercado Libre", "JBL Perú"}


class _PriceFetchStatusError(RuntimeError):
    def __init__(self, status_code: int):
        self.status_code = int(status_code)
        self.trace_status = "FETCH_NOT_FOUND" if self.status_code in {404, 410} else "FETCH_BLOCKED"
        super().__init__(f"HTTP {self.status_code}")


def _ensure_usable_price_fetch(result) -> None:
    raw = getattr(result, "status_code", None)
    if raw is None:
        return
    try:
        status = int(raw)
    except (TypeError, ValueError):
        return
    if status >= 400:
        raise _PriceFetchStatusError(status)


def _query(identity: ProductIdentity) -> str:
    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or "").strip()


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


def _mercadolibre_terminal_status(exc: MercadoLibreAuthError) -> str:
    code = str(getattr(exc, "code", "") or "").upper()
    if code == "ML_AUTH_NOT_CONFIGURED":
        return "ML_NOT_CONFIGURED"
    if code in {"ML_REFRESH_TOKEN_INVALID", "ML_CLIENT_CREDENTIALS_INVALID", "ERROR_AUTH_MERCADOLIBRE"}:
        return "ML_AUTH_FAILED"
    return "ML_ACCESS_BLOCKED"


def _mercadolibre_queries(identity: ProductIdentity) -> list[str]:
    return [row.query for row in build_price_query_plan(identity, limit=12)]


def _try_mercadolibre(identity: ProductIdentity, timeout: int = 15, on_query_event=None) -> list[PriceOffer]:
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
    _ensure_usable_price_fetch(fetched)
    final_url = str(getattr(fetched, "final_url", None) or url)
    html = str(getattr(fetched, "html", "") or "")
    page_rows = extract_page_offers(html, final_url, identity, channel=channel)
    if not page_rows and channel in BROWSER_PRICE_CHANNELS and getattr(fetched, "method", "") != "playwright":
        try:
            rendered = fetch_page(url, timeout=35, browser_fallback=True, prefer_browser=True, activate_lazy_media=False)
            _ensure_usable_price_fetch(rendered)
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
        _ensure_usable_price_fetch(fetched)
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



def _collect_direct_source_offers(
    capabilities: list[dict],
    identity: ProductIdentity,
    emit,
    *,
    trace: PriceCoverageTrace | None = None,
    capability_registry: SourceCapabilityRegistry | None = None,
) -> list[PriceOffer]:
    """Freshly query proven source-native capabilities without cached product answers."""
    capabilities = [dict(row) for row in capabilities if row.get("domain") and row.get("direct_method")]
    if not capabilities:
        return []

    category = classify_product(identity).category

    def worker(capability: dict) -> list[PriceOffer]:
        domain = str(capability.get("domain") or "").strip().casefold().removeprefix("www.")
        method = str(capability.get("direct_method") or "").strip()
        platform = str(capability.get("platform") or "").strip() or None
        base_url = f"https://{domain}"
        channel = _channel_from_url(base_url)
        if trace:
            trace.record(channel, "FETCH_STARTED", url=base_url)
        emit(
            "source",
            channel=channel,
            domain=domain,
            status="fetching",
            method=method,
            recovery_method="DIRECT_SOURCE",
        )
        try:
            if method == "vtex_catalog":
                found = _try_vtex(base_url, identity, channel, timeout=10)
            else:
                found = []
            found = dedupe_offers(found)
            extraction = next((str(row.source_method or "").strip() for row in found if str(row.source_method or "").strip()), method or None)
            if capability_registry is not None:
                try:
                    capability_registry.record(
                        domain,
                        platform=platform,
                        discovery_method=f"direct_{method}" if method else "direct_source",
                        extraction_method=extraction,
                        price_capable=True if found else None,
                        stock_capable=True if any(row.stock is not None or bool(row.availability) for row in found) else None,
                        seller_capable=True if any(bool(row.seller_display_name or row.seller_legal_name or row.seller_tax_id) for row in found) else None,
                        success=bool(found),
                        category=category,
                    )
                except Exception:
                    # Capability memory is advisory. A persistence failure must never
                    # discard a fresh offer already returned by the source adapter.
                    pass
            if trace:
                trace.record(channel, "FETCH_OK", url=base_url)
                trace.record(channel, "IDENTITY_ACCEPTED" if found else "PARSER_ZERO_OFFERS", url=base_url)
            emit(
                "source",
                channel=channel,
                domain=domain,
                status="ok",
                offers=len(found),
                method=method,
                recovery_method="DIRECT_SOURCE",
            )
            return found
        except Exception as exc:
            if capability_registry is not None:
                try:
                    capability_registry.record(
                        domain,
                        platform=platform,
                        discovery_method=f"direct_{method}" if method else "direct_source",
                        success=False,
                        category=category,
                    )
                except Exception:
                    pass
            if trace:
                trace.record(channel, "FETCH_BLOCKED", url=base_url, detail=type(exc).__name__)
            emit(
                "source",
                channel=channel,
                domain=domain,
                status="error",
                method=method,
                recovery_method="DIRECT_SOURCE",
                terminal="DIRECT_SOURCE_FAILED",
                error=f"{type(exc).__name__}: {exc}",
            )
            return []

    rows: list[PriceOffer] = []
    workers = max(1, min(4, len(capabilities)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="price-direct-source") as pool:
        futures = [pool.submit(worker, capability) for capability in capabilities]
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except Exception:
                # Worker already isolates expected source errors; this is a final
                # safety boundary so one source can never block the other lanes.
                continue
    return dedupe_offers(rows)

def _remember_source_capability(registry, url: str, html: str, rows: list[PriceOffer], identity: ProductIdentity, discovery_method: str | None, *, success: bool) -> None:
    if registry is None:
        return
    methods = list(dict.fromkeys(str(row.source_method or "").strip() for row in rows if str(row.source_method or "").strip()))
    extraction_method = methods[0] if len(methods) == 1 else "multi" if methods else None
    try:
        registry.record(
            url,
            platform=detect_ecommerce_platform(url, html),
            discovery_method=discovery_method,
            extraction_method=extraction_method,
            price_capable=bool(rows),
            stock_capable=any(row.stock is not None or bool(row.availability) for row in rows),
            seller_capable=any(bool(row.seller_display_name or row.seller_legal_name or row.seller_tax_id) for row in rows),
            success=success,
            category=classify_product(identity).category,
        )
    except Exception:
        # Source memory is advisory. Persistence failure must never abort a price run.
        pass


def _collect_web_offers(
    sources: list[str],
    identity: ProductIdentity,
    emit,
    *,
    trace: PriceCoverageTrace | None = None,
    capability_registry: SourceCapabilityRegistry | None = None,
    discovery_method: str | None = None,
) -> list[PriceOffer]:
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
            _remember_source_capability(capability_registry, url, html, augmented, identity, discovery_method, success=bool(augmented))
            if trace:
                trace.record(channel, "FETCH_OK", url=url)
                trace.record(channel, "PARSER_STARTED", url=url)
                if augmented:
                    trace.record(channel, "IDENTITY_ACCEPTED", url=url)
                else:
                    trace.record(channel, "PARSER_ZERO_OFFERS", url=url)
            emit("page", url=url, channel=channel, status="parsed", offers=len(augmented))
        except Exception as exc:
            _remember_source_capability(capability_registry, url, "", [], identity, discovery_method, success=False)
            if trace:
                trace_status = getattr(exc, "trace_status", None)
                if trace_status:
                    trace.record(channel, trace_status, url=url, detail=f"HTTP_{getattr(exc, 'status_code', 0)}")
                elif isinstance(exc, (requests.Timeout, TimeoutError)):
                    trace.record(channel, "FETCH_TIMEOUT", url=url, detail=type(exc).__name__)
                else:
                    trace.record(channel, "FETCH_BLOCKED", url=url, detail=type(exc).__name__)
            emit("page", url=url, channel=channel, status="error", error=f"{type(exc).__name__}: {exc}")
    return rows


def _has_trusted_offer(rows: list[PriceOffer]) -> bool:
    return any(_is_trusted_final_offer(row) for row in dedupe_offers(rows))


def run_price_product(identity: ProductIdentity, output_root: str | Path, *, on_event=None, max_sources: int = 48) -> list[PriceOffer]:
    def emit(event_type: str, **payload):
        if on_event:
            on_event({"type": event_type, "identity": identity.model_dump(), **payload})

    def emit_query(payload: dict):
        emit("query", **payload)

    resolution = resolve_price_identity(identity)
    working_identity = resolution.identity
    trace = PriceCoverageTrace()
    capability_registry = SourceCapabilityRegistry(output_root)
    emit(
        "identity",
        input_identity=identity.model_dump(),
        resolved_identity=working_identity.model_dump(),
        resolution_status=resolution.status,
        resolution_confidence=resolution.confidence,
        resolution_reason=resolution.reason,
        evidence_backed=resolution.evidence_backed,
        official_domain_hint=resolution.official_domain_hint,
        candidate_urls=list(resolution.candidate_urls),
        page_signals=list(resolution.page_signals),
    )

    offers: list[PriceOffer] = []
    structured_domains = tuple(
        (urlparse(base_url).hostname or "").casefold().removeprefix("www.")
        for _channel, base_url in PERU_STRUCTURED_SOURCES
    )
    direct_capabilities = capability_registry.direct_candidates(
        working_identity,
        limit=max(1, min(8, max_sources // 6 or 1)),
        exclude_domains=structured_domains,
    )
    direct_rows: list[PriceOffer] = []
    if direct_capabilities:
        emit(
            "source_routing",
            recovery_method="DIRECT_SOURCE",
            candidates=len(direct_capabilities),
            domains=[row.get("domain") for row in direct_capabilities],
        )
        direct_rows = _collect_direct_source_offers(
            direct_capabilities,
            working_identity,
            emit,
            trace=trace,
            capability_registry=capability_registry,
        )
        offers.extend(direct_rows)

    direct_candidate_domains = {str(row.get("domain") or "").casefold().removeprefix("www.") for row in direct_capabilities}
    direct_success_domains = {
        (urlparse(row.url).hostname or "").casefold().removeprefix("www.")
        for row in direct_rows
        if (urlparse(row.url).hostname or "")
    }
    direct_success_domains = {
        domain for domain in direct_success_domains
        if domain in direct_candidate_domains or any(domain.endswith("." + candidate) for candidate in direct_candidate_domains)
    }
    provider_limit = max(1, min(4, max_sources // 12 or 1))
    excluded_provider_domains = tuple(dict.fromkeys((*structured_domains, *sorted(direct_success_domains))))
    failed_direct_domains = [
        domain for domain in (str(row.get("domain") or "").casefold().removeprefix("www.") for row in direct_capabilities)
        if domain and domain not in direct_success_domains and domain not in structured_domains
    ]
    ranked_provider_domains = capability_registry.provider_fallback_domains(
        working_identity,
        limit=provider_limit,
        exclude_domains=excluded_provider_domains,
    )
    priority_domains = tuple(dict.fromkeys((*failed_direct_domains, *ranked_provider_domains)))[:provider_limit]
    if priority_domains:
        emit(
            "source_routing",
            recovery_method="LEARNED_PROVIDER_FALLBACK",
            candidates=len(priority_domains),
            domains=list(priority_domains),
        )
    learned_sources = load_validated_source_urls(output_root, identity)
    warm_path = bool(learned_sources)
    emit("status", stage="searching", message="Consultando APIs y fuentes estructuradas de Perú")

    for channel, base_url in PERU_STRUCTURED_SOURCES:
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

    try:
        ml = _try_mercadolibre(working_identity, on_query_event=emit_query)
        offers.extend(ml)
        if ml:
            trace.record("MercadoLibre", "IDENTITY_ACCEPTED")
        else:
            trace.record("MercadoLibre", "QUERY_EXECUTED_NO_RESULT")
        emit("source", channel="MercadoLibre", status="ok", offers=len(ml), method="mercadolibre_mpe")
    except MercadoLibreAuthError as exc:
        terminal = _mercadolibre_terminal_status(exc)
        trace.record("MercadoLibre", terminal, detail=exc.code)
        emit("source", channel="MercadoLibre", status="error", terminal=terminal, error_code=exc.code, error=str(exc))
    except Exception as exc:
        trace.record("MercadoLibre", "ML_ACCESS_BLOCKED", detail=type(exc).__name__)
        emit("source", channel="MercadoLibre", status="error", terminal="ML_ACCESS_BLOCKED", error=f"{type(exc).__name__}: {exc}")

    retail_sources: list[str] = []
    if warm_path:
        emit("source", channel="learned", status="refreshing", urls=len(learned_sources), method="validated_source_memory")
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="price-warm") as pool:
            learned_future = pool.submit(_refresh_learned_sources, learned_sources, working_identity, emit)
            retail_future = pool.submit(
                discover_general_peru_retailers,
                working_identity,
                limit=max(10, max_sources // 2),
                priority_domains=priority_domains,
                on_query_event=emit_query,
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
        offers.extend(_collect_web_offers(
            fresh_retail[:max_sources], working_identity, emit, trace=trace,
            capability_registry=capability_registry, discovery_method="open_web",
        ))

    marketplace_sources: list[str] = []
    base_sources: list[str] = []
    if not warm_path or not _has_trusted_offer(offers):
        try:
            marketplace_sources = discover_additional_peru_pdps(working_identity, limit_per_domain=max(4, min(10, max_sources // 4 or 4)), on_query_event=emit_query)
            emit("source", channel="peru_directed", status="ok", offers=0, urls=len(marketplace_sources), method="targeted_pdp")
        except Exception as exc:
            emit("source", channel="peru_directed", status="error", error=f"discovery: {type(exc).__name__}: {exc}")
        if not warm_path:
            try:
                retail_sources = discover_general_peru_retailers(
                    working_identity, limit=max(10, max_sources // 2), priority_domains=priority_domains,
                    on_query_event=emit_query,
                )
                emit("source", channel="peru_retail", status="ok", offers=0, urls=len(retail_sources), method="identifier_and_alias_retail")
            except Exception as exc:
                emit("source", channel="peru_retail", status="error", error=f"discovery: {type(exc).__name__}: {exc}")
        try:
            base_sources = discover_price_sources(working_identity, limit=max_sources)
            emit("source", channel="web", status="ok", offers=0, urls=len(base_sources), method="generic_peru")
        except Exception as exc:
            emit("source", channel="web", status="error", error=f"discovery: {type(exc).__name__}: {exc}")

        skip_urls = set(learned_sources) if warm_path else set()
        sources = [
            url
            for url in _merge_sources(marketplace_sources, retail_sources, base_sources, limit=max_sources)
            if url not in skip_urls
        ]
        offers.extend(_collect_web_offers(
            sources, working_identity, emit, trace=trace,
            capability_registry=capability_registry, discovery_method="mixed_web",
        ))

    deduped = dedupe_offers(offers)
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
    emit("status", stage="saving", message=f"Guardando {len(valid)} ofertas peruanas validadas")
    save_price_run(output_root, valid)
    save_validated_source_bindings(output_root, identity, valid)
    save_channel_coverage(output_root, coverage)
    emit("coverage", report=coverage)
    for row in valid:
        emit("offer", offer=row.to_dict())
    emit(
        "done",
        offers=len(valid),
        channels=len({r.channel for r in valid}),
        sellers=len({competitor_key(r) for r in valid}),
        target_channels_found=sum(1 for row in coverage["channels"] if row.get("offers")),
        individual_stores=coverage["individual_store_count"],
        best_by_currency=_best_by_currency(valid),
        candidate_offers=len(offers),
        deduped_offers=len(deduped),
        duplicates=max(0, len(offers) - len(deduped)),
        trusted_offers=len(trusted),
        price_rejected=max(0, len(deduped) - len(trusted)) + len(rejected_outliers),
    )
    return valid