from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests

from .models import ProductIdentity
from .price_adapters import parse_mercadolibre_payload, parse_vtex_payload
from .price_discovery import discover_price_sources, extract_page_offers
from .price_history import save_price_run
from .price_identity import dedupe_offers, is_peru_offer
from .price_models import PriceOffer
from .price_peru_coverage import discover_additional_peru_pdps
from .web_fetch import fetch_page

PERU_STRUCTURED_SOURCES: tuple[tuple[str, str], ...] = (
    ("Falabella", "https://www.falabella.com.pe"),
    ("PlazaVea", "https://www.plazavea.com.pe"),
    ("Oechsle", "https://www.oechsle.pe"),
)


def _query(identity: ProductIdentity) -> str:
    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or "").strip()


def _channel_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "web").lower().removeprefix("www.")
    names = {"falabella":"Falabella","ripley":"Ripley","plazavea":"PlazaVea","oechsle":"Oechsle","mercadolibre":"MercadoLibre","sodimac":"Sodimac","jbl":"JBL Perú"}
    for key, name in names.items():
        if key in host:
            return name
    return (host.split(".")[0] if host else "Web").replace("-", " ").title()


def _mercadolibre_queries(identity: ProductIdentity) -> list[str]:
    values = [
        _query(identity),
        " ".join(v for v in (identity.brand, identity.model or identity.product_name) if v).strip(),
        str(identity.model or identity.product_name or "").strip(),
    ]
    return list(dict.fromkeys(v for v in values if v))


def _try_mercadolibre(identity: ProductIdentity, timeout: int = 15) -> list[PriceOffer]:
    rows: list[PriceOffer] = []
    for q in _mercadolibre_queries(identity):
        url = f"https://api.mercadolibre.com/sites/MPE/search?q={quote_plus(q)}&limit=50"
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "ProductIntelligence/0.10"})
        response.raise_for_status()
        rows.extend(parse_mercadolibre_payload(response.json(), identity))
    # Preserve independently published listings; final workflow dedupe uses
    # publication_id/seller rather than collapsing the whole marketplace.
    return dedupe_offers(rows)


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


def _best_by_currency(offers: list[PriceOffer]) -> dict[str, float]:
    best: dict[str, float] = {}
    for row in offers:
        currency = str(row.currency or "").upper() or "UNKNOWN"
        current = best.get(currency)
        if current is None or row.selling_price < current:
            best[currency] = row.selling_price
    return best


def _merge_sources(*groups: list[str], limit: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for url in group:
            clean = str(url or "").strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            merged.append(clean)
            if len(merged) >= limit:
                return merged
    return merged


def run_price_product(identity: ProductIdentity, output_root: str | Path, *, on_event=None, max_sources: int = 40) -> list[PriceOffer]:
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

    additional: list[str] = []
    base_sources: list[str] = []
    try:
        additional = discover_additional_peru_pdps(identity, limit_per_domain=max(4, min(8, max_sources // 5 or 4)))
    except Exception as exc:
        emit("source", channel="peru_directed", status="error", error=f"discovery: {type(exc).__name__}: {exc}")
    try:
        base_sources = discover_price_sources(identity, limit=max_sources)
    except Exception as exc:
        emit("source", channel="web", status="error", error=f"discovery: {type(exc).__name__}: {exc}")

    sources = _merge_sources(additional, base_sources, limit=max_sources)
    emit("status", stage="validating", message=f"Revisando {len(sources)} publicaciones web de Perú")
    for pos, url in enumerate(sources, 1):
        channel = _channel_from_url(url)
        try:
            emit("page", url=url, channel=channel, position=pos, total=len(sources), status="fetching")
            fetched = fetch_page(url, timeout=25, browser_fallback=True, activate_lazy_media=False)
            final_url = str(getattr(fetched, "final_url", None) or url)
            html = str(getattr(fetched, "html", "") or "")
            if "vtex" in html.lower() or "vteximg" in html.lower() or "/api/catalog_system/" in html.lower():
                try:
                    vtex_rows = _try_vtex(final_url, identity, channel)
                    offers.extend(vtex_rows)
                    if vtex_rows:
                        emit("offer", channel=channel, count=len(vtex_rows), method="vtex")
                except Exception as exc:
                    emit("source", channel=channel, status="error", error=f"vtex: {type(exc).__name__}: {exc}")
            page_rows = extract_page_offers(html, final_url, identity, channel=channel)
            offers.extend(page_rows)
            emit("page", url=final_url, channel=channel, status="parsed", offers=len(page_rows))
        except Exception as exc:
            emit("page", url=url, channel=channel, status="error", error=f"{type(exc).__name__}: {exc}")

    deduped = dedupe_offers(offers)
    valid = [row for row in deduped if is_peru_offer(row) and row.confidence >= 0.70 and row.selling_price > 0]
    emit("status", stage="saving", message=f"Guardando {len(valid)} ofertas peruanas validadas")
    save_price_run(output_root, valid)
    for row in valid:
        emit("offer", offer=row.to_dict())
    emit("done", offers=len(valid), channels=len({r.channel for r in valid}), sellers=len({(r.channel, r.seller_display_name) for r in valid}), best_by_currency=_best_by_currency(valid))
    return valid
