from __future__ import annotations

import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from .html_extract import identity_from_page
from .identity_gate import ObservedIdentity
from .models import ProductIdentity
from .page_type import PageSignals
from .source_authority import AuthoritySignals


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _type_values(obj: dict) -> list[str]:
    raw = obj.get("@type", obj.get("type"))
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if raw:
        return [str(raw)]
    return []


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def derive_observed_identity(expected: ProductIdentity, page: dict) -> ObservedIdentity:
    """Build observed identity without seeding model/name fields from the request."""
    candidate = identity_from_page(page, expected=None)
    text = str(page.get("text") or "")
    compact_text = _compact(text)

    def seen(value: str | None) -> bool:
        token = _compact(value)
        return bool(token and token in compact_text)

    mpns = []
    gtins = []
    eans = []
    upcs = []

    if candidate.mpn:
        mpns.append(str(candidate.mpn))
    if candidate.gtin:
        gtins.append(str(candidate.gtin))
    if candidate.ean:
        eans.append(str(candidate.ean))
    if candidate.upc:
        upcs.append(str(candidate.upc))

    # Literal appearance of a requested strong identifier in page content is an observed signal,
    # not a copied identity value. This preserves exact pages that lack structured Product markup.
    if expected.mpn and seen(expected.mpn) and expected.mpn not in mpns:
        mpns.append(expected.mpn)
    if expected.gtin and seen(expected.gtin) and expected.gtin not in gtins:
        gtins.append(expected.gtin)
    if expected.ean and seen(expected.ean) and expected.ean not in eans:
        eans.append(expected.ean)
    if expected.upc and seen(expected.upc) and expected.upc not in upcs:
        upcs.append(expected.upc)

    return ObservedIdentity(
        brand=candidate.brand,
        model=candidate.model,
        product_name=candidate.product_name,
        mpns=tuple(dict.fromkeys(mpns)),
        gtins=tuple(dict.fromkeys(gtins)),
        eans=tuple(dict.fromkeys(eans)),
        upcs=tuple(dict.fromkeys(upcs)),
    )


def derive_page_signals(html: str, url: str, page: dict) -> PageSignals:
    soup = BeautifulSoup(html or "", "lxml")
    h1 = soup.find("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else ""

    objects = list(_walk_dicts(page.get("jsonld", []))) + list(_walk_dicts(page.get("embedded", {})))
    schema_types: list[str] = []
    product_entities = 0
    organization_entities = 0
    for obj in objects:
        types = _type_values(obj)
        schema_types.extend(types)
        lowered = {t.lower() for t in types}
        if any(t.endswith("product") or t == "product" for t in lowered):
            product_entities += 1
        if any(t.endswith("organization") or t == "organization" for t in lowered):
            organization_entities += 1

    product_cards = 0
    for node in soup.find_all(attrs={"itemtype": re.compile(r"schema\.org/Product", re.I)}):
        product_cards += 1
    product_cards += len(soup.select("[data-product-id], [data-product-sku], .product-card, .product-tile"))

    spec_blocks = len(soup.find_all("table")) + len(soup.find_all("dl"))
    spec_blocks += len(soup.select("[class*='spec'], [id*='spec'], [class*='technical'], [id*='technical']"))

    path = (urlparse(url).path or "").lower()
    title_h1 = f"{page.get('title') or ''} {h1_text}".lower()
    update_signal = any(x in title_h1 or x in path for x in ("software update", "firmware update", "notify update", "release notes", "/update"))
    legal_signal = any(x in path for x in ("/privacy", "/terms", "/cookies", "/legal"))
    account_signal = any(x in path for x in ("/account", "/login", "/signin", "/register"))
    search_signal = "/search" in path or "search results" in title_h1
    generic_support_signal = any(x in path for x in ("/support", "/help")) and product_entities == 0 and spec_blocks == 0

    return PageSignals(
        url=url,
        content_type="text/html",
        title=str(page.get("title") or ""),
        h1=h1_text,
        schema_types=tuple(dict.fromkeys(schema_types)),
        product_entity_count=product_entities,
        product_card_count=product_cards,
        specification_block_count=spec_blocks,
        download_link_count=len(page.get("pdfs", [])) + len(page.get("document_links", [])),
        update_signal=update_signal,
        legal_signal=legal_signal,
        account_signal=account_signal,
        search_signal=search_signal,
        generic_support_signal=generic_support_signal,
    )


def derive_authority_signals(expected: ProductIdentity, html: str, url: str, page: dict) -> AuthoritySignals:
    soup = BeautifulSoup(html or "", "lxml")
    objects = list(_walk_dicts(page.get("jsonld", []))) + list(_walk_dicts(page.get("embedded", {})))

    org_names: list[str] = []
    explicit_manufacturer = None
    for obj in objects:
        types = {t.lower() for t in _type_values(obj)}
        if any(t.endswith("organization") or t == "organization" for t in types):
            name = obj.get("name")
            if name:
                org_names.append(str(name))
        manufacturer = obj.get("manufacturer")
        if isinstance(manufacturer, dict):
            manufacturer = manufacturer.get("name")
        if manufacturer and not explicit_manufacturer:
            explicit_manufacturer = str(manufacturer)

    canonical = soup.find("link", rel=lambda v: v and "canonical" in [str(x).lower() for x in (v if isinstance(v, list) else [v])])
    canonical_host = None
    if canonical and canonical.get("href"):
        canonical_host = (urlparse(canonical.get("href")).hostname or "").lower().removeprefix("www.")

    base_host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    same_origin_product_links = 0
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href") or ""
        parsed = urlparse(href)
        host = (parsed.hostname or base_host).lower().removeprefix("www.")
        path = (parsed.path or href).lower()
        if host == base_host and any(token in path for token in ("/product", "/products/", "/p/")):
            same_origin_product_links += 1

    footer = soup.find("footer")
    footer_text = footer.get_text(" ", strip=True) if footer else ""
    brand = _compact(expected.brand)
    footer_compact = _compact(footer_text)
    brand_owned_footer = bool(brand and brand in footer_compact and any(x in footer_text.lower() for x in ("copyright", "©", "all rights reserved")))

    path = (urlparse(url).path or "").lower()
    support_signal = any(x in path for x in ("/support", "/downloads", "/manual", "/help"))
    host = base_host
    marketplace_signal = any(x in host for x in ("amazon.", "ebay.", "mercadolibre.", "falabella.", "ripley."))

    return AuthoritySignals(
        url=url,
        requested_brand=expected.brand,
        organization_names=tuple(dict.fromkeys(org_names)),
        canonical_host=canonical_host,
        same_origin_product_links=same_origin_product_links,
        brand_owned_footer=brand_owned_footer,
        explicit_manufacturer_name=explicit_manufacturer,
        support_signal=support_signal,
        marketplace_signal=marketplace_signal,
    )
