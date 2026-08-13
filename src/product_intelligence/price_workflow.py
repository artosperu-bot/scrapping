from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests

from .models import ProductIdentity
from .price_adapters import parse_mercadolibre_payload, parse_shopify_product_payload, parse_vtex_payload
from .price_discovery import discover_price_sources, extract_page_offers
from .price_history import save_price_run
from .price_identity import competitor_key, dedupe_offers, filter_market_outliers, is_peru_offer
from .price_models import PriceOffer
from .price_peru_coverage import discover_additional_peru_pdps, discover_general_peru_retailers
from .web_fetch import fetch_page

PERU_STRUCTURED_SOURCES: tuple[tuple[str, str], ...] = (
    ("Falabella", "https://www.falabella.com.pe"),
    ("PlazaVea", "https://www.plazavea.com.pe"),
    ("Oechsle", "https://www.oechsle.pe"),
)

STRICT_MARKETPLACE_CHANNELS = {"falabella","ripley","plazavea","oechsle","mercadolibre","sodimac","jblperu"}
BROWSER_PRICE_CHANNELS = {"Ripley", "MercadoLibre", "JBL Perú"}


def _query(identity: ProductIdentity) -> str:
    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or "").strip()


def _channel_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "web").lower().removeprefix("www.")
    names = {
        "falabella":"Falabella","ripley":"Ripley","plazavea":"PlazaVea","oechsle":"Oechsle",
        "mercadolibre":"MercadoLibre","sodimac":"Sodimac","jbl":"JBL Perú","infiniti":"Infiniti",
        "perudataconsult":"Peru Data","arteus":"Arteus","baetech":"BaeTech","panacompu":"Pana Compu",
        "memorykings":"Memory Kings","estuyo":"EsTuyo","bigmarket":"Big Market","efe":"Efe",
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
    for q in queries:
        try:
            url = f"https://api.mercadolibre.com/sites/MPE/search?q={quote_plus(q)}&limit=50"
            response = requests.get(url, timeout=timeout, headers={"User-Agent": "ProductIntelligence/0.10"})
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


def run_price_product(identity: ProductIdentity, output_root: str | Path, *, on_event=None, max_sources: int = 48) -> list[PriceOffer]:
    def emit(event_type: str, **payload):
        if on_event:
            on_event({"type": event_type, "identity": identity.model_dump(), **payload})

    offers: list[PriceOffer] = []
    emit("status", stage="searching", message="Consultando APIs y fuentes estructuradas de Perú")

    for channel, base_url in PERU_STRUCTURED_SOURCES:
        try:
            rows = _try_vtex(base_url, identity, channel)
            offers.extend(rows)
            emit("source", channel=channel, status="ok", offers=len(rows), method="structured_direct")
        except Exception as exc:
            emit("source", channel=channel, status="error", error=f"structured: {type(exc).__name__}: {exc}")

    try:
        ml = _try_mercadolibre(identity)
        offers.extend(ml)
        emit("source", channel="MercadoLibre", status="ok", offers=len(ml), method="mercadolibre_mpe")
    except Exception as exc:
        emit("source", channel="MercadoLibre", status="error", error=f"{type(exc).__name__}: {exc}")

    marketplace_sources: list[str] = []
    retail_sources: list[str] = []
    base_sources: list[str] = []
    try:
        marketplace_sources = discover_additional_peru_pdps(identity, limit_per_domain=max(4, min(10, max_sources // 4 or 4)))
        emit("source", channel="peru_directed", status="ok", offers=0, urls=len(marketplace_sources), method="targeted_pdp")
    except Exception as exc:
        emit("source", channel="peru_directed", status="error", error=f"discovery: {type(exc).__name__}: {exc}")
    try:
        retail_sources = discover_general_peru_retailers(identity, limit=max(10, max_sources // 2))
        emit("source", channel="peru_retail", status="ok", offers=0, urls=len(retail_sources), method="exact_identifier_retail")
    except Exception as exc:
        emit("source", channel="peru_retail", status="error", error=f"discovery: {type(exc).__name__}: {exc}")
    try:
        base_sources = discover_price_sources(identity, limit=max_sources)
        emit("source", channel="web", status="ok", offers=0, urls=len(base_sources), method="generic_peru")
    except Exception as exc:
        emit("source", channel="web", status="error", error=f"discovery: {type(exc).__name__}: {exc}")

    sources = _merge_sources(marketplace_sources, retail_sources, base_sources, limit=max_sources)
    emit("status", stage="validating", message=f"Revisando {len(sources)} publicaciones web de Perú")
    for pos, url in enumerate(sources, 1):
        channel = _channel_from_url(url)
        try:
            emit("page", url=url, channel=channel, position=pos, total=len(sources), status="fetching")
            html, page_rows = _parse_page_with_dynamic_retry(url, identity, channel, emit)
            if "vtex" in html.lower() or "vteximg" in html.lower() or "/api/catalog_system/" in html.lower():
                try:
                    vtex_rows = _try_vtex(url, identity, channel)
                    offers.extend(vtex_rows)
                    if vtex_rows:
                        emit("offer", channel=channel, count=len(vtex_rows), method="vtex")
                except Exception as exc:
                    emit("source", channel=channel, status="error", error=f"vtex: {type(exc).__name__}: {exc}")
            try:
                shopify_rows = _try_shopify(url, identity, channel)
                offers.extend(shopify_rows)
                if shopify_rows:
                    emit("offer", channel=channel, count=len(shopify_rows), method="shopify_product_json")
            except Exception as exc:
                emit("source", channel=channel, status="error", error=f"shopify: {type(exc).__name__}: {exc}")
            offers.extend(page_rows)
            emit("page", url=url, channel=channel, status="parsed", offers=len(page_rows))
        except Exception as exc:
            emit("page", url=url, channel=channel, status="error", error=f"{type(exc).__name__}: {exc}")

    deduped = dedupe_offers(offers)
    trusted = [row for row in deduped if _is_trusted_final_offer(row)]
    valid, rejected_outliers = filter_market_outliers(trusted)
    if rejected_outliers:
        emit("quality", rejected_outliers=len(rejected_outliers), prices=[r.selling_price for r in rejected_outliers])
    emit("status", stage="saving", message=f"Guardando {len(valid)} ofertas peruanas validadas")
    save_price_run(output_root, valid)
    for row in valid:
        emit("offer", offer=row.to_dict())
    emit(
        "done",
        offers=len(valid),
        channels=len({r.channel for r in valid}),
        sellers=len({competitor_key(r) for r in valid}),
        best_by_currency=_best_by_currency(valid),
    )
    return valid
