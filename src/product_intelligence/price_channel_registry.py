from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .price_models import PriceOffer


@dataclass(frozen=True, slots=True)
class ChannelSpec:
    label: str
    domains: tuple[str, ...]
    aliases: tuple[str, ...] = ()


TARGET_CHANNELS: tuple[ChannelSpec, ...] = (
    ChannelSpec("Falabella", ("falabella.com.pe",), ("Saga", "Saga Falabella")),
    ChannelSpec("Ripley", ("simple.ripley.com.pe", "ripley.com.pe")),
    ChannelSpec("Mercado Libre", ("mercadolibre.com.pe",), ("MercadoLibre",)),
    ChannelSpec("Real Plaza", ("realplaza.com",)),
    ChannelSpec("Tiendas EFE", ("efe.com.pe",), ("Efe", "Conecta", "Conecta Retail")),
    ChannelSpec("Coolbox", ("coolbox.pe",)),
    ChannelSpec("Juntoz", ("juntoz.com",)),
    ChannelSpec("Claro", ("tienda.claro.com.pe", "claro.com.pe")),
    ChannelSpec("Plaza Vea", ("plazavea.com.pe",), ("PlazaVea",)),
    ChannelSpec("Promart", ("promart.pe",)),
    ChannelSpec("Oechsle", ("oechsle.pe",), ("OESHLE",)),
    ChannelSpec("Wong", ("wong.pe",), ("Tiendas Wong",)),
    ChannelSpec("Metro", ("metro.pe",)),
    ChannelSpec("Tottus", ("tottus.com.pe",)),
    ChannelSpec("Sodimac", ("sodimac.com.pe",)),
)


def _key(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").casefold().removeprefix("www.")


def _matches_domain(host: str, domain: str) -> bool:
    domain = domain.casefold().removeprefix("www.")
    return host == domain or host.endswith("." + domain)


def target_spec_for_name(value: str | None) -> ChannelSpec | None:
    wanted = _key(value)
    if not wanted:
        return None
    for spec in TARGET_CHANNELS:
        if wanted == _key(spec.label) or any(wanted == _key(alias) for alias in spec.aliases):
            return spec
    return None


def target_spec_for_url(url: str) -> ChannelSpec | None:
    host = _host(url)
    for spec in TARGET_CHANNELS:
        if any(_matches_domain(host, domain) for domain in spec.domains):
            return spec
    return None


def channel_from_url(url: str) -> str:
    spec = target_spec_for_url(url)
    if spec:
        return spec.label
    host = _host(url)
    return (host.split(".")[0] if host else "Web").replace("-", " ").title()


def is_target_channel_offer(row: PriceOffer) -> bool:
    return bool(target_spec_for_name(row.channel) or target_spec_for_url(row.url))


def _offer_row(row: PriceOffer, *, channel: str | None = None) -> dict:
    seller = row.seller_display_name or row.seller_legal_name or row.channel
    return {
        "channel": channel or row.channel,
        "seller": seller,
        "price": row.selling_price,
        "list_price": row.list_price,
        "currency": row.currency,
        "stock": row.stock,
        "availability": row.availability,
        "url": row.url,
        "source_method": row.source_method,
        "identity_match": row.identity_match,
        "confidence": row.confidence,
    }


def build_channel_coverage(offers: list[PriceOffer]) -> dict:
    grouped: dict[str, list[PriceOffer]] = {spec.label: [] for spec in TARGET_CHANNELS}
    individual: list[PriceOffer] = []
    for row in offers:
        spec = target_spec_for_name(row.channel) or target_spec_for_url(row.url)
        if spec:
            grouped[spec.label].append(row)
        else:
            individual.append(row)

    channels = []
    for spec in TARGET_CHANNELS:
        rows = sorted(grouped[spec.label], key=lambda item: item.selling_price)
        channels.append({
            "channel": spec.label,
            "aliases": list(spec.aliases),
            "status": "FOUND" if rows else "NO_HAY",
            "offers": [_offer_row(row, channel=spec.label) for row in rows],
        })

    individual_rows = [_offer_row(row) for row in sorted(individual, key=lambda item: item.selling_price)]
    return {
        "channels": channels,
        "individual_stores": individual_rows,
        "individual_store_count": len(individual_rows),
    }
