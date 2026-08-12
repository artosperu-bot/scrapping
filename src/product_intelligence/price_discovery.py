from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .discovery import search_web
from .models import ProductIdentity
from .price_identity import score_offer_identity
from .price_models import PriceOffer


def _channel(url: str) -> str:
    host = (urlparse(url).hostname or "web").lower().removeprefix("www.")
    first = host.split(".")[0] if host else "web"
    return first.replace("-", " ").title()


def discover_price_sources(identity: ProductIdentity, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for candidate in search_web(identity, limit=limit):
        url = str(getattr(candidate, "url", "") or "").strip()
        if url.startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            out.append(url)
    return out[:limit]


def _walk_jsonld(value):
    if isinstance(value, list):
        for item in value:
            yield from _walk_jsonld(item)
    elif isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if graph:
            yield from _walk_jsonld(graph)


def _money(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^0-9.,]", "", value).replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def extract_page_offers(html: str, url: str, identity: ProductIdentity, channel: str | None = None) -> list[PriceOffer]:
    soup = BeautifulSoup(html or "", "lxml")
    page_text = soup.get_text(" ", strip=True)[:500000]
    base_evidence = {
        "mpn": identity.mpn if identity.mpn and identity.mpn.lower() in (html or "").lower() else None,
        "brand": identity.brand if identity.brand and identity.brand.lower() in page_text.lower() else None,
        "model": identity.model if identity.model and identity.model.lower() in page_text.lower() else page_text[:250],
        "title": soup.title.get_text(" ", strip=True) if soup.title else page_text[:250],
    }
    default_channel = channel or _channel(url)
    rows: list[PriceOffer] = []

    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        try:
            payload = json.loads(script.string or script.get_text() or "null")
        except Exception:
            continue
        for node in _walk_jsonld(payload):
            typ = node.get("@type")
            types = {str(x).lower() for x in (typ if isinstance(typ, list) else [typ]) if x}
            if "product" not in types:
                continue
            evidence = dict(base_evidence)
            evidence.update({
                "mpn": node.get("mpn") or base_evidence.get("mpn"),
                "brand": (node.get("brand") or {}).get("name") if isinstance(node.get("brand"), dict) else node.get("brand") or base_evidence.get("brand"),
                "model": node.get("model") or node.get("name") or base_evidence.get("model"),
                "gtin": node.get("gtin13") or node.get("gtin12") or node.get("gtin") or node.get("sku"),
                "title": node.get("name") or base_evidence.get("title"),
            })
            score, match, conflicts = score_offer_identity(identity, evidence)
            if score < 0.70 or conflicts:
                continue
            offers = node.get("offers")
            offers = offers if isinstance(offers, list) else [offers] if isinstance(offers, dict) else []
            for offer in offers:
                price = _money(offer.get("price") or offer.get("lowPrice"))
                if not price or price <= 0:
                    continue
                seller = offer.get("seller") or {}
                seller_name = seller.get("name") if isinstance(seller, dict) else str(seller or "") or None
                rows.append(PriceOffer(
                    part_number=identity.mpn,
                    brand=identity.brand,
                    model=identity.model or identity.product_name,
                    channel=default_channel,
                    seller_display_name=seller_name,
                    selling_price=price,
                    list_price=_money(offer.get("highPrice")),
                    currency=str(offer.get("priceCurrency") or "PEN"),
                    availability=str(offer.get("availability") or "") or None,
                    condition=str(offer.get("itemCondition") or "") or None,
                    url=str(offer.get("url") or url),
                    confidence=score,
                    identity_match=match,
                    source_type="structured",
                    source_method="jsonld",
                    sku=str(node.get("sku") or "") or None,
                    evidence=evidence,
                ))

    if rows:
        return rows

    score, match, conflicts = score_offer_identity(identity, base_evidence)
    if score < 0.70 or conflicts:
        return []
    meta_price = None
    meta_currency = "PEN"
    for key in ("product:price:amount", "og:price:amount"):
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            meta_price = _money(tag.get("content"))
            if meta_price:
                break
    tag = soup.find("meta", attrs={"property": "product:price:currency"})
    if tag and tag.get("content"):
        meta_currency = str(tag.get("content"))
    if not meta_price:
        match_price = re.search(r"(?:S/\.?|S\s*/|PEN\s*)\s*([0-9]{1,6}(?:[.,][0-9]{1,2})?)", page_text, re.I)
        meta_price = _money(match_price.group(1)) if match_price else None
    if meta_price and meta_price > 0:
        return [PriceOffer(part_number=identity.mpn, brand=identity.brand, model=identity.model or identity.product_name, channel=default_channel, seller_display_name=None, selling_price=meta_price, currency=meta_currency, url=url, confidence=min(score, 0.95), identity_match=match, source_type="web", source_method="html", evidence=base_evidence)]
    return []
