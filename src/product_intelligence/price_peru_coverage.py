from __future__ import annotations

import re
from urllib.parse import urlparse

from .discovery import search_web_query
from .models import ProductIdentity


PERU_MARKETPLACE_DOMAINS: tuple[str, ...] = (
    "falabella.com.pe",
    "simple.ripley.com.pe",
    "mercadolibre.com.pe",
    "plazavea.com.pe",
    "oechsle.pe",
    "sodimac.com.pe",
    "jbl.com.pe",
)

# Seed domains are not exclusive sources. They are high-value Peru retailers found
# to expose exact product identifiers and prices on public PDPs. Generic Peru retail
# discovery below still searches beyond this list for every new product.
PERU_RETAIL_HINT_DOMAINS: tuple[str, ...] = (
    "infiniti.com.pe",
    "perudataconsult.net",
    "arteus.pe",
    "baetech.pe",
    "panacompu.com",
    "memorykings.pe",
    "estuyo.pe",
    "bigmarketperu.com",
    "efe.com.pe",
)

_LISTING_MARKERS = (
    "/category/",
    "/categoria/",
    "/search/",
    "/buscar/",
    "/landing/",
    "/collections/",
    "/pages/",
)
_PRODUCT_MARKERS = (
    "/product/",
    "/products/",
    "/shop/",
    "/informacion-producto/",
    "/product-information/",
)


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _host_matches(url: str, domain: str) -> bool:
    host = _host(url)
    return host == domain or host.endswith("." + domain)


def _strong(identity: ProductIdentity) -> str:
    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or "").strip()


def _is_pdp(url: str, domain: str, strong: str) -> bool:
    path = (urlparse(url).path or "").lower()
    if any(marker in path for marker in _LISTING_MARKERS):
        return False
    if domain == "falabella.com.pe":
        return "/product/" in path
    if domain == "simple.ripley.com.pe":
        return "pmp" in path or _compact(strong) in _compact(path)
    if domain == "mercadolibre.com.pe":
        return "/p/" in path or "/up/" in path
    if domain in {"plazavea.com.pe", "oechsle.pe"}:
        return path.rstrip("/").endswith("/p")
    if domain == "sodimac.com.pe":
        return "/articulo/" in path
    if domain == "jbl.com.pe":
        return bool(_compact(strong) and _compact(strong) in _compact(path))
    return False


def _deterministic_pdps(identity: ProductIdentity) -> list[str]:
    """Safe official-store URLs whose route is based on a public product identifier."""
    rows: list[str] = []
    if _compact(identity.brand) == "jbl" and identity.mpn:
        rows.append(f"https://www.jbl.com.pe/{str(identity.mpn).strip()}.html")
    return rows


def _queries(identity: ProductIdentity, domain: str) -> list[str]:
    strong = _strong(identity)
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    queries = [f'"{strong}" site:{domain}']
    if model:
        queries.extend([
            f'"{strong}" "{model}" site:{domain}',
            f'"{model}" {brand} site:{domain}'.strip(),
        ])
    if domain == "falabella.com.pe":
        queries.extend([
            f'"{strong}" site:falabella.com.pe/falabella-pe/product',
            f'"{strong}" "Vendido por" site:falabella.com.pe',
            f'"{strong}" "Modelo" site:falabella.com.pe/falabella-pe/product',
        ])
    elif domain == "simple.ripley.com.pe":
        queries.extend([
            f'"{strong}" site:simple.ripley.com.pe pmp',
            f'"{strong}" "Vendido por" site:simple.ripley.com.pe',
            f'"{strong}" "Internet" site:simple.ripley.com.pe',
            f'"{model}" "Internet" site:simple.ripley.com.pe pmp' if model else "",
        ])
    elif domain == "mercadolibre.com.pe":
        queries.extend([
            f'"{strong}" site:mercadolibre.com.pe/p',
            f'"{strong}" site:mercadolibre.com.pe/up',
            f'"{strong}" "Modelo alfanumérico" site:mercadolibre.com.pe',
            f'"{strong}" "Modelo detallado" site:mercadolibre.com.pe',
        ])
    elif domain == "plazavea.com.pe":
        queries.extend([
            f'"{strong}" site:plazavea.com.pe "/p"',
            f'"{strong}" "Vendido por" site:plazavea.com.pe',
        ])
    elif domain == "oechsle.pe":
        queries.extend([
            f'"{strong}" site:oechsle.pe "/p"',
            f'"{strong}" "Vendido por" site:oechsle.pe',
        ])
    elif domain == "sodimac.com.pe":
        queries.append(f'"{strong}" site:sodimac.com.pe/sodimac-pe/articulo')
    elif domain == "jbl.com.pe" and model:
        queries.append(f'"{model}" site:jbl.com.pe')
    return list(dict.fromkeys(q for q in queries if q.strip()))


def discover_additional_peru_pdps(
    identity: ProductIdentity,
    *,
    limit_per_domain: int = 10,
    domains: tuple[str, ...] = PERU_MARKETPLACE_DOMAINS,
) -> list[str]:
    """Return multiple PDP candidates per Peru marketplace."""
    strong = _strong(identity)
    if not strong:
        return []
    per_domain: list[list[str]] = []
    for domain in domains:
        found_domain: list[str] = []
        seen: set[str] = set()
        for seed in _deterministic_pdps(identity):
            if _host_matches(seed, domain) and _is_pdp(seed, domain, strong):
                seen.add(seed)
                found_domain.append(seed)
        for query in _queries(identity, domain):
            try:
                urls = search_web_query(identity, query, limit=limit_per_domain, timeout=12)
            except Exception:
                urls = []
            for raw in urls:
                url = str(raw or "").strip()
                if not url.startswith(("http://", "https://")):
                    continue
                if url in seen or not _host_matches(url, domain) or not _is_pdp(url, domain, strong):
                    continue
                seen.add(url)
                found_domain.append(url)
                if len(found_domain) >= limit_per_domain:
                    break
            if len(found_domain) >= limit_per_domain:
                break
        per_domain.append(found_domain)

    merged: list[str] = []
    seen_all: set[str] = set()
    for index in range(limit_per_domain):
        for rows in per_domain:
            if index < len(rows) and rows[index] not in seen_all:
                seen_all.add(rows[index])
                merged.append(rows[index])
    return merged


def _is_peru_retail_candidate(url: str, strong: str) -> bool:
    parsed = urlparse(url)
    host = _host(url)
    path = (parsed.path or "").lower()
    if not host or any(marker in path for marker in _LISTING_MARKERS):
        return False
    if any(_host_matches(url, domain) for domain in PERU_MARKETPLACE_DOMAINS):
        return False

    cc_peru = host.endswith(".pe") or host.endswith(".com.pe")
    hinted = any(_host_matches(url, domain) for domain in PERU_RETAIL_HINT_DOMAINS)
    peru_path = "/peru/" in path or path.startswith("/peru")
    if not (cc_peru or hinted or peru_path):
        return False

    strong_in_url = bool(_compact(strong) and _compact(strong) in _compact(url))
    productish = any(marker in path for marker in _PRODUCT_MARKERS)
    return strong_in_url or productish


def _general_retail_queries(identity: ProductIdentity) -> list[str]:
    strong = _strong(identity)
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    queries = [
        f'"{strong}" precio Perú',
        f'"{strong}" "S/" Perú',
        f'"{strong}" tienda Perú',
        f'"{strong}" comprar Perú',
    ]
    if model:
        queries.extend([
            f'"{strong}" "{model}" Perú',
            f'"{model}" "{strong}" {brand} Perú'.strip(),
        ])
    for domain in PERU_RETAIL_HINT_DOMAINS:
        queries.append(f'"{strong}" site:{domain}')
    return list(dict.fromkeys(q for q in queries if q.strip()))


def discover_general_peru_retailers(identity: ProductIdentity, *, limit: int = 20) -> list[str]:
    """Discover exact-product PDPs from Peru retailers beyond the big marketplaces.

    Discovery is intentionally broad; acceptance is intentionally strict. A URL found
    here still has to pass the normal exact identity/structured-offer validation before
    it can become a saved price offer.
    """
    strong = _strong(identity)
    if not strong or limit <= 0:
        return []

    rows: list[str] = []
    seen: set[str] = set()
    per_query = max(6, min(20, limit * 2))
    for query in _general_retail_queries(identity):
        try:
            found = search_web_query(identity, query, limit=per_query, timeout=12)
        except Exception:
            found = []
        for raw in found:
            url = str(raw or "").strip()
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            if not _is_peru_retail_candidate(url, strong):
                continue
            seen.add(url)
            rows.append(url)
            if len(rows) >= limit:
                return rows
    return rows
