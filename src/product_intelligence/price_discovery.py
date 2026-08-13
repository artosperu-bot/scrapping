from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .discovery import search_web, search_web_query
from .models import ProductIdentity
from .price_identity import score_offer_identity
from .price_models import PriceOffer


PERU_PRICE_DOMAINS = (
    "falabella.com.pe",
    "simple.ripley.com.pe",
    "mercadolibre.com.pe",
    "plazavea.com.pe",
    "oechsle.pe",
    "sodimac.com.pe",
    "jbl.com.pe",
)

TARGETED_PERU_DOMAINS = (
    "falabella.com.pe",
    "simple.ripley.com.pe",
    "sodimac.com.pe",
    "jbl.com.pe",
)


def _channel(url: str) -> str:
    host = (urlparse(url).hostname or "web").lower().removeprefix("www.")
    names = {
        "falabella": "Falabella",
        "ripley": "Ripley",
        "plazavea": "PlazaVea",
        "oechsle": "Oechsle",
        "mercadolibre": "MercadoLibre",
        "sodimac": "Sodimac",
        "jbl": "JBL Perú",
    }
    for key, value in names.items():
        if key in host:
            return value
    first = host.split(".")[0] if host else "web"
    return first.replace("-", " ").title()


def _priority_rank(url: str, priority_domains: tuple[str, ...]) -> tuple[int, int]:
    host = (urlparse(url).hostname or "").lower()
    for index, domain in enumerate(priority_domains):
        if host == domain or host.endswith("." + domain):
            return (0, index)
    return (1, len(priority_domains))


def _host_matches(url: str, domain: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == domain or host.endswith("." + domain)


def _identity_query(identity: ProductIdentity) -> str:
    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or "").strip()


def discover_targeted_peru_sources(
    identity: ProductIdentity,
    *,
    limit_per_domain: int = 5,
    domains: tuple[str, ...] = TARGETED_PERU_DOMAINS,
) -> list[str]:
    """Discover exact-product pages in priority Peru channels, interleaved by channel."""
    strong = _identity_query(identity)
    if not strong:
        return []
    per_domain: list[list[str]] = []
    for domain in domains:
        query = f'"{strong}" site:{domain}'
        try:
            found = search_web_query(identity, query, limit=limit_per_domain, timeout=12)
        except Exception:
            found = []
        clean_rows: list[str] = []
        seen_local: set[str] = set()
        for url in found:
            clean = str(url or "").strip()
            if clean.startswith(("http://", "https://")) and _host_matches(clean, domain) and clean not in seen_local:
                seen_local.add(clean)
                clean_rows.append(clean)
        per_domain.append(clean_rows)

    # Round-robin prevents five Falabella listings from hiding Ripley/JBL/Sodimac.
    urls: list[str] = []
    seen: set[str] = set()
    for index in range(limit_per_domain):
        for rows in per_domain:
            if index < len(rows) and rows[index] not in seen:
                seen.add(rows[index])
                urls.append(rows[index])
    return urls


def discover_price_sources(
    identity: ProductIdentity,
    limit: int = 12,
    *,
    priority_domains: tuple[str, ...] = PERU_PRICE_DOMAINS,
) -> list[str]:
    # Deterministic domain-targeted Peru discovery comes first. Generic discovery is
    # additive fallback rather than the mechanism that decides whether a key channel
    # gets checked at all.
    targeted = discover_targeted_peru_sources(identity, limit_per_domain=max(2, min(5, limit)))
    candidates = search_web(identity, limit=max(limit * 3, 24))
    urls: list[str] = []
    seen: set[str] = set()
    for url in targeted:
        if url not in seen:
            seen.add(url)
            urls.append(url)
    generic: list[str] = []
    for candidate in candidates:
        url = str(getattr(candidate, "url", "") or "").strip()
        if url.startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            generic.append(url)
    generic.sort(key=lambda value: _priority_rank(value, priority_domains))
    urls.extend(generic)
    return urls[:limit]


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


def _seller_from_text(text: str) -> str | None:
    patterns = [
        r"Vendido\s+por\s*:\s*([A-Za-zÁÉÍÓÚÑáéíóúñ0-9._& -]{2,70}?)(?=\s+(?:Normal|Internet|Seller Info|Producto publicado|Realiza|Cumple|Ofrece|No existe|S/|Código|Cód\.|$))",
        r"Vendido\s+por\s+([A-Za-zÁÉÍÓÚÑáéíóúñ0-9._& -]{2,70}?)(?=\s+(?:Seller Info|Producto publicado|Realiza|Cumple|Ofrece|No existe|S/|Código|Cód\.|$))",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip(" :-")
    return None


def _legal_identity_from_text(text: str) -> tuple[str | None, str | None]:
    ruc_m = re.search(r"\bRUC\s*:?[ ]*(\d{11})\b", text, re.I)
    legal_m = re.search(
        r"\b([A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9 .&-]{2,80}?(?:S\.?A\.?C\.?|E\.?I\.?R\.?L\.?|S\.?R\.?L\.?))\b",
        text,
    )
    return (legal_m.group(1).strip() if legal_m else None, ruc_m.group(1) if ruc_m else None)


def _peru_marketplace_html_offer(
    page_text: str,
    url: str,
    identity: ProductIdentity,
    channel: str,
    evidence: dict,
) -> list[PriceOffer]:
    score, match, conflicts = score_offer_identity(identity, evidence)
    if score < 0.95 or conflicts:
        return []

    host = (urlparse(url).hostname or "").lower()
    seller = _seller_from_text(page_text)
    legal_name, tax_id = _legal_identity_from_text(page_text)
    selling = None
    list_price = None

    if "ripley.com.pe" in host:
        internet = re.search(r"Internet\s*S\s*/\s*([0-9][0-9.,]*)", page_text, re.I)
        normal = re.search(r"Normal\s*S\s*/\s*([0-9][0-9.,]*)", page_text, re.I)
        selling = _money(internet.group(1)) if internet else None
        list_price = _money(normal.group(1)) if normal else None
    elif "falabella.com.pe" in host or "sodimac.com.pe" in host:
        lower = page_text.lower()
        start = lower.find("vendido por")
        segment = page_text[start : start + 1200] if start >= 0 else page_text[:2500]
        values = [_money(v) for v in re.findall(r"S\s*/\s*([0-9][0-9.,]*)", segment, re.I)]
        values = [v for v in values if v and v > 0]
        if values:
            selling = values[0]
            list_price = values[1] if len(values) > 1 and values[1] >= values[0] else None
    elif "jbl.com.pe" in host:
        m = re.search(r"S\s*/\s*([0-9][0-9.,]*)", page_text, re.I)
        selling = _money(m.group(1)) if m else None
        seller = seller or "JBL Perú"

    if not selling or selling <= 0:
        return []

    return [PriceOffer(
        part_number=identity.mpn,
        brand=identity.brand,
        model=identity.model or identity.product_name,
        channel=channel,
        seller_display_name=seller,
        seller_legal_name=legal_name,
        seller_tax_id=tax_id,
        selling_price=selling,
        list_price=list_price,
        currency="PEN",
        url=url,
        confidence=score,
        identity_match=match,
        source_type="web",
        source_method="marketplace_html",
        evidence=evidence,
    )]


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

    marketplace_rows = _peru_marketplace_html_offer(page_text, url, identity, default_channel, base_evidence)
    if marketplace_rows:
        return marketplace_rows

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
                offer_url = str(offer.get("url") or url).strip()
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
                    url=urljoin(url, offer_url),
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
