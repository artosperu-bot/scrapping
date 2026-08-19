from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .discovery import search_web, search_web_query
from .models import ProductIdentity
from .identifiers import canonical_gtin, clean_identifier_value
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


def _is_peru_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if any(_host_matches(url, domain) for domain in PERU_PRICE_DOMAINS):
        return True
    return host.endswith(".pe") or host.endswith(".com.pe")


def _is_targeted_marketplace_url(url: str) -> bool:
    return any(_host_matches(url, domain) for domain in TARGETED_PERU_DOMAINS)


def _identity_query(identity: ProductIdentity) -> str:
    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or "").strip()


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _is_target_product_detail_url(url: str, domain: str, strong: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    if any(marker in path for marker in ("/category/", "/categoria/", "/search/", "/buscar/")):
        return False
    if domain == "falabella.com.pe":
        return "/product/" in path
    if domain == "simple.ripley.com.pe":
        return "pmp" in path or (_compact(strong) in _compact(path) and "/tecnologia/" not in path)
    if domain == "sodimac.com.pe":
        return "/articulo/" in path
    if domain == "jbl.com.pe":
        return bool(_compact(strong) and _compact(strong) in _compact(path))
    return True


def _is_known_target_listing_url(url: str, identity: ProductIdentity) -> bool:
    strong = _identity_query(identity)
    for domain in TARGETED_PERU_DOMAINS:
        if _host_matches(url, domain):
            return not _is_target_product_detail_url(url, domain, strong)
    return False


def _targeted_queries(domain: str, strong: str) -> list[str]:
    queries = [f'"{strong}" site:{domain}']
    if domain == "falabella.com.pe":
        queries.append(f'"{strong}" site:falabella.com.pe/falabella-pe/product')
    elif domain == "simple.ripley.com.pe":
        queries.append(f'"{strong}" site:simple.ripley.com.pe pmp')
    elif domain == "sodimac.com.pe":
        queries.append(f'"{strong}" site:sodimac.com.pe/sodimac-pe/articulo')
    return queries


def _directed_search(identity: ProductIdentity, query: str, *, limit: int, domain: str) -> list[str]:
    """Use domain-aware admission while tolerating legacy injected search callables.

    The real search_web_query supports required_domain. The TypeError retry only keeps
    older test/plugin callables with the pre-required_domain signature compatible;
    returned URLs are still domain-checked below before admission.
    """
    try:
        return search_web_query(identity, query, limit=limit, timeout=12, required_domain=domain)
    except TypeError as exc:
        if "required_domain" not in str(exc):
            raise
        return search_web_query(identity, query, limit=limit, timeout=12)


def discover_targeted_peru_sources(
    identity: ProductIdentity,
    *,
    limit_per_domain: int = 5,
    domains: tuple[str, ...] = TARGETED_PERU_DOMAINS,
) -> list[str]:
    """Find multiple exact-product PDP candidates per priority Peru channel."""
    strong = _identity_query(identity)
    if not strong:
        return []
    per_domain: list[list[str]] = []
    for domain in domains:
        clean_rows: list[str] = []
        seen_local: set[str] = set()
        for query in _targeted_queries(domain, strong):
            try:
                found = _directed_search(identity, query, limit=limit_per_domain, domain=domain)
            except Exception:
                found = []
            for url in found:
                clean = str(url or "").strip()
                if (
                    clean.startswith(("http://", "https://"))
                    and _host_matches(clean, domain)
                    and _is_target_product_detail_url(clean, domain, strong)
                    and clean not in seen_local
                ):
                    seen_local.add(clean)
                    clean_rows.append(clean)
                    if len(clean_rows) >= limit_per_domain:
                        break
            if len(clean_rows) >= limit_per_domain:
                break
        per_domain.append(clean_rows)

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
    limit: int = 24,
    *,
    priority_domains: tuple[str, ...] = PERU_PRICE_DOMAINS,
) -> list[str]:
    per_domain = max(3, min(5, max(1, limit // 4)))
    targeted = discover_targeted_peru_sources(identity, limit_per_domain=per_domain)
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
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        if not _is_peru_url(url):
            continue
        if _is_known_target_listing_url(url, identity):
            continue
        seen.add(url)
        generic.append(url)
    generic.sort(key=lambda value: _priority_rank(value, priority_domains))

    remaining = max(0, limit - len(urls))
    urls.extend(generic[:remaining])
    return urls


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


_NON_PRODUCT_PRICE_CONTEXT = (
    "cuota", "cuotas", "mensual", "al mes", "por mes", "envío", "envio", "delivery", "shipping",
    "despacho", "por kg", "/kg", "kilogram", "precio por unidad", "unit price", "financiamiento",
    "cupón", "cupon", "coupon", "precio lista", "precio regular", "precio normal", "list price", "antes",
)
_PRODUCT_PRICE_CONTEXT = (
    "precio internet", "precio online", "precio oferta", "precio con tarjeta", "precio efectivo",
    "precio venta", "precio", "oferta", "ahora", "venta",
)


def _visible_product_price(text: str) -> float | None:
    matches = list(re.finditer(r"(?:S/\.?|S\s*/|PEN\s*)\s*([0-9]{1,7}(?:[.,][0-9]{1,2})?)", text or "", re.I))
    candidates: list[tuple[int, int, float]] = []
    for index, match in enumerate(matches):
        price = _money(match.group(1))
        if not price or price <= 0:
            continue
        previous_end = matches[index - 1].end() if index else max(0, match.start() - 80)
        next_start = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), match.end() + 80)
        start = max(previous_end, match.start() - 60)
        end = min(next_start, match.end() + 60)
        context = text[start:end].casefold()
        if any(marker in context for marker in _NON_PRODUCT_PRICE_CONTEXT):
            continue
        positive = sum(1 for marker in _PRODUCT_PRICE_CONTEXT if marker in context)
        candidates.append((positive, match.start(), price))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (-row[0], row[1]))
    return candidates[0][2]


def _seller_from_text(text: str) -> str | None:
    patterns = [
        r"Vendido\s+por\s*:\s*([A-Za-zÁÉÍÓÚÑáéíóúñ0-9._& -]{2,120}?)(?=\s+(?:Normal|Internet|Seller Info|Producto publicado|Realiza|Cumple|Ofrece|No existe|S/|Código|Cód\.|$))",
        r"Vendido\s+por\s+([A-Za-zÁÉÍÓÚÑáéíóúñ0-9._& -]{2,120}?)(?=\s+(?:Seller Info|Producto publicado|Realiza|Cumple|Ofrece|No existe|S/|Código|Cód\.|$))",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if not m:
            continue
        value = m.group(1).strip(" :-")
        legal_boundary = re.search(
            r"\s+[A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9 .&-]{2,80}?(?:S\.?A\.?C\.?|E\.?I\.?R\.?L\.?|S\.?R\.?L\.?)\b",
            value,
        )
        if legal_boundary:
            value = value[: legal_boundary.start()].strip()
        value = re.split(r"\s+RUC\s*:?\s*\d{0,11}\b", value, maxsplit=1, flags=re.I)[0].strip()
        return value or None
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
    elif "falabella.com.pe" in host:
        lower = page_text.lower()
        start = lower.find("vendido por")
        segment = page_text[start : start + 1200] if start >= 0 else page_text[:2500]
        values = [_money(v) for v in re.findall(r"S\s*/\s*([0-9][0-9.,]*)", segment, re.I)]
        values = [v for v in values if v and v > 0]
        if values:
            selling = values[0]
            list_price = values[1] if len(values) > 1 and values[1] >= values[0] else None
    elif "sodimac.com.pe" in host:
        lower = page_text.lower()
        start = lower.find("vendido por")
        segment = page_text[start : start + 1200] if start >= 0 else page_text[:2500]
        values = [_money(v) for v in re.findall(r"S\s*/\s*([0-9][0-9.,]*)", segment, re.I)]
        values = [v for v in values if v and v > 0]
        if len(values) >= 2:
            selling = values[0]
            list_price = values[1] if values[1] >= values[0] else None
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
    if _is_known_target_listing_url(url, identity):
        return []

    soup = BeautifulSoup(html or "", "lxml")
    page_text = soup.get_text(" ", strip=True)[:500000]
    title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.find("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else ""
    primary_identity_text = f"{url} {title_text} {h1_text}".strip()
    primary_lower = primary_identity_text.lower()
    observed_model = h1_text or title_text or page_text[:250]
    base_evidence = {
        "mpn": identity.mpn if identity.mpn and identity.mpn.lower() in primary_lower else None,
        "brand": identity.brand if identity.brand and identity.brand.lower() in primary_lower else None,
        "model": observed_model,
        "title": title_text or h1_text or page_text[:250],
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
                "gtin": canonical_gtin(node.get("gtin14") or node.get("gtin13") or node.get("gtin12") or node.get("gtin8") or node.get("gtin")),
                "sku": clean_identifier_value(node.get("sku")),
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
                    sku=clean_identifier_value(node.get("sku")),
                    evidence=evidence,
                ))

    if rows:
        return rows

    if _is_targeted_marketplace_url(url):
        return []

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
        meta_price = _visible_product_price(page_text)
    if meta_price and meta_price > 0:
        return [PriceOffer(
            part_number=identity.mpn,
            brand=identity.brand,
            model=identity.model or identity.product_name,
            channel=default_channel,
            seller_display_name=None,
            selling_price=meta_price,
            currency=meta_currency,
            url=url,
            confidence=min(score, 0.95),
            identity_match=match,
            source_type="web",
            source_method="html",
            evidence=base_evidence,
        )]
    return []