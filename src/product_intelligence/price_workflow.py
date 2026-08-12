from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests

from .models import ProductIdentity
from .price_adapters import parse_mercadolibre_payload, parse_vtex_payload
from .price_discovery import discover_price_sources, extract_page_offers
from .price_history import save_price_run
from .price_identity import dedupe_offers
from .price_models import PriceOffer
from .web_fetch import fetch_page


def _query(identity: ProductIdentity) -> str:
    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or "").strip()


def _channel_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "web").lower().removeprefix("www.")
    names = {"falabella": "Falabella", "ripley": "Ripley", "plazavea": "PlazaVea", "oechsle": "Oechsle", "mercadolibre": "MercadoLibre"}
    for key, name in names.items():
        if key in host:
            return name
    return (host.split(".")[0] if host else "Web").replace("-", " ").title()


def _try_mercadolibre(identity: ProductIdentity, timeout: int = 15) -> list[PriceOffer]:
    q = _query(identity)
    if not q:
        return []
    url = f"https://api.mercadolibre.com/sites/MPE/search?q={quote_plus(q)}"
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "ProductIntelligence/0.10"})
    response.raise_for_status()
    return parse_mercadolibre_payload(response.json(), identity)


def _try_vtex(url: str, identity: ProductIdentity, channel: str, timeout: int = 15) -> list[PriceOffer]:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    endpoint = f"{origin}/api/catalog_system/pub/products/search?ft={quote_plus(_query(identity))}"
    response = requests.get(endpoint, timeout=timeout, headers={"User-Agent": "ProductIntelligence/0.10"})
    if response.status_code != 200:
        return []
    data = response.json()
    if not isinstance(data, (list, dict)):
        return []
    return parse_vtex_payload(data, identity, channel=channel, source_url=url)


def _best_by_currency(offers: list[PriceOffer]) -> dict[str, float]:
    best: dict[str, float] = {}
    for row in offers:
        currency = str(row.currency or "").upper() or "UNKNOWN"
        current = best.get(currency)
        if current is None or row.selling_price < current:
            best[currency] = row.selling_price
    return best


def run_price_product(
    identity: ProductIdentity,
    output_root: str | Path,
    *,
    on_event=None,
    max_sources: int = 12,
) -> list[PriceOffer]:
    def emit(event_type: str, **payload):
        if on_event:
            on_event({"type": event_type, "identity": identity.model_dump(), **payload})

    offers: list[PriceOffer] = []
    emit("status", stage="searching", message="Consultando fuentes estructuradas")

    try:
        ml = _try_mercadolibre(identity)
        offers.extend(ml)
        emit("source", channel="MercadoLibre", status="ok", offers=len(ml))
    except Exception as exc:
        emit("source", channel="MercadoLibre", status="error", error=f"{type(exc).__name__}: {exc}")

    try:
        sources = discover_price_sources(identity, limit=max_sources)
    except Exception as exc:
        sources = []
        emit("source", channel="web", status="error", error=f"discovery: {type(exc).__name__}: {exc}")

    emit("status", stage="validating", message=f"Revisando {len(sources)} fuentes web")
    for pos, url in enumerate(sources, 1):
        channel = _channel_from_url(url)
        try:
            emit("page", url=url, channel=channel, position=pos, total=len(sources), status="fetching")
            fetched = fetch_page(url, timeout=25, browser_fallback=True, activate_lazy_media=False)
            final_url = str(getattr(fetched, "final_url", None) or url)
            html = str(getattr(fetched, "html", "") or "")

            # VTEX is attempted only after real page evidence is observed.
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

    valid = [row for row in dedupe_offers(offers) if row.confidence >= 0.70 and row.selling_price > 0]
    emit("status", stage="saving", message=f"Guardando {len(valid)} ofertas validadas")
    save_price_run(output_root, valid)
    for row in valid:
        emit("offer", offer=row.to_dict())
    emit(
        "done",
        offers=len(valid),
        channels=len({r.channel for r in valid}),
        best_by_currency=_best_by_currency(valid),
    )
    return valid
