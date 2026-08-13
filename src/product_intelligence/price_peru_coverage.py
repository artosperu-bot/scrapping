from __future__ import annotations

import re
from urllib.parse import urlparse

from .discovery import search_web_query
from .models import ProductIdentity
from .price_channel_registry import TARGET_CHANNELS

PERU_TARGET_DOMAINS: tuple[str, ...] = tuple(dict.fromkeys(
    domain for spec in TARGET_CHANNELS for domain in spec.domains
))
PERU_MARKETPLACE_DOMAINS: tuple[str, ...] = PERU_TARGET_DOMAINS + ("jbl.com.pe",)
PERU_RETAIL_HINT_DOMAINS: tuple[str, ...] = (
    "infiniti.com.pe", "perudataconsult.net", "arteus.pe", "baetech.pe",
    "panacompu.com", "memorykings.pe", "estuyo.pe", "bigmarketperu.com", "efe.com.pe",
)
_LISTING_MARKERS = ("/category/", "/categoria/", "/search/", "/buscar/", "/landing/", "/collections/", "/pages/", "/lista/")
# /product intentionally covers product/products/producto/productos.
_PRODUCT_MARKERS = ("/product", "/shop/", "/informacion-producto/", "/product-information/", "/articulo/")


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _host_matches(url: str, domain: str) -> bool:
    host = _host(url)
    return host == domain or host.endswith("." + domain)


def _strong_identifiers(identity: ProductIdentity) -> list[str]:
    out, seen = [], set()
    for value in (identity.mpn, identity.ean, identity.upc, identity.gtin):
        clean = str(value or "").strip()
        key = _compact(clean)
        if clean and key and key not in seen:
            seen.add(key)
            out.append(clean)
    return out


def _strong(identity: ProductIdentity) -> str:
    ids = _strong_identifiers(identity)
    return ids[0] if ids else str(identity.model or identity.product_name or "").strip()


def _alias_identity(identity: ProductIdentity) -> ProductIdentity:
    """Discovery-only identity: retain semantics but remove strong IDs from search ranking."""
    data = identity.model_dump()
    for field in ("mpn", "ean", "upc", "gtin", "sku"):
        data[field] = None
    return ProductIdentity(**data)


def _is_pdp(url: str, domain: str, strong: str) -> bool:
    path = (urlparse(url).path or "").lower()
    if any(marker in path for marker in _LISTING_MARKERS):
        return False
    if domain == "falabella.com.pe": return "/product/" in path
    if domain in {"simple.ripley.com.pe", "ripley.com.pe"}: return "pmp" in path or _compact(strong) in _compact(path)
    if domain == "mercadolibre.com.pe": return "/p/" in path or "/up/" in path
    if domain in {"plazavea.com.pe", "oechsle.pe", "realplaza.com", "tienda.claro.com.pe", "claro.com.pe"}: return path.rstrip("/").endswith("/p") or any(marker in path for marker in _PRODUCT_MARKERS)
    if domain == "sodimac.com.pe": return "/articulo/" in path
    if domain == "jbl.com.pe": return bool(_compact(strong) and _compact(strong) in _compact(path))
    return bool(any(marker in path for marker in _PRODUCT_MARKERS) or path.rstrip("/").endswith("/p") or path.endswith(".html"))


def _deterministic_pdps(identity: ProductIdentity) -> list[str]:
    if _compact(identity.brand) == "jbl" and identity.mpn:
        return [f"https://www.jbl.com.pe/{str(identity.mpn).strip()}.html"]
    return []


def _queries(identity: ProductIdentity, domain: str) -> list[str]:
    strong = _strong(identity)
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    q = [f'"{strong}" site:{domain}']
    if model:
        q += [f'"{strong}" "{model}" site:{domain}', f'"{model}" {brand} site:{domain}'.strip()]
    extras = {
        "falabella.com.pe": [
            f'"{strong}" site:falabella.com.pe/falabella-pe/product',
            f'"{strong}" "Vendido por" site:falabella.com.pe',
            f'"{strong}" "Modelo" site:falabella.com.pe/falabella-pe/product'],
        "simple.ripley.com.pe": [
            f'"{strong}" site:simple.ripley.com.pe pmp',
            f'"{strong}" "Vendido por" site:simple.ripley.com.pe',
            f'"{strong}" "Internet" site:simple.ripley.com.pe',
            f'"{model}" "Internet" site:simple.ripley.com.pe pmp' if model else ""],
        "mercadolibre.com.pe": [
            f'"{strong}" site:mercadolibre.com.pe/p', f'"{strong}" site:mercadolibre.com.pe/up',
            f'"{strong}" "Modelo alfanumérico" site:mercadolibre.com.pe',
            f'"{strong}" "Modelo detallado" site:mercadolibre.com.pe'],
        "plazavea.com.pe": [f'"{strong}" site:plazavea.com.pe "/p"', f'"{strong}" "Vendido por" site:plazavea.com.pe'],
        "oechsle.pe": [f'"{strong}" site:oechsle.pe "/p"', f'"{strong}" "Vendido por" site:oechsle.pe'],
        "sodimac.com.pe": [f'"{strong}" site:sodimac.com.pe/sodimac-pe/articulo'],
        "jbl.com.pe": [f'"{model}" site:jbl.com.pe'] if model else [],
    }
    q += extras.get(domain, [])
    return list(dict.fromkeys(x for x in q if x.strip()))


def _alias_queries(identity: ProductIdentity, domain: str) -> list[str]:
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    if not model:
        return []
    return list(dict.fromkeys([
        f'"{model}" "{brand}" site:{domain}'.strip(),
        f'"{model}" site:{domain}',
    ]))


def discover_additional_peru_pdps(identity: ProductIdentity, *, limit_per_domain: int = 10, domains: tuple[str, ...] = PERU_MARKETPLACE_DOMAINS) -> list[str]:
    strong = _strong(identity)
    if not strong: return []
    alias_identity = _alias_identity(identity)
    model = str(identity.model or identity.product_name or "").strip()
    per_domain = []
    for domain in domains:
        found, seen = [], set()
        for seed in _deterministic_pdps(identity):
            if _host_matches(seed, domain) and _is_pdp(seed, domain, strong):
                seen.add(seed); found.append(seed)
        for query in _queries(identity, domain):
            try: urls = search_web_query(identity, query, limit=limit_per_domain, timeout=12)
            except Exception: urls = []
            for raw in urls:
                url = str(raw or "").strip()
                if not url.startswith(("http://", "https://")) or url in seen: continue
                if not _host_matches(url, domain) or not _is_pdp(url, domain, strong): continue
                seen.add(url); found.append(url)
                if len(found) >= limit_per_domain: break
            if len(found) >= limit_per_domain: break
        if len(found) < limit_per_domain and model:
            for query in _alias_queries(identity, domain):
                try: urls = search_web_query(alias_identity, query, limit=limit_per_domain, timeout=12)
                except Exception: urls = []
                for raw in urls:
                    url = str(raw or "").strip()
                    if not url.startswith(("http://", "https://")) or url in seen: continue
                    if not _host_matches(url, domain) or not _is_pdp(url, domain, model): continue
                    seen.add(url); found.append(url)
                    if len(found) >= limit_per_domain: break
                if len(found) >= limit_per_domain: break
        per_domain.append(found)
    merged, seen_all = [], set()
    for index in range(limit_per_domain):
        for rows in per_domain:
            if index < len(rows) and rows[index] not in seen_all:
                seen_all.add(rows[index]); merged.append(rows[index])
    return merged


def _is_peru_retail_candidate(url: str, strong: str) -> bool:
    path, host = (urlparse(url).path or "").lower(), _host(url)
    if not host or any(marker in path for marker in _LISTING_MARKERS): return False
    if any(_host_matches(url, domain) for domain in PERU_MARKETPLACE_DOMAINS): return False
    local = host.endswith(".pe") or host.endswith(".com.pe")
    hinted = any(_host_matches(url, domain) for domain in PERU_RETAIL_HINT_DOMAINS)
    peru_path = path.startswith("/peru")
    if not (local or hinted or peru_path): return False
    return bool((_compact(strong) and _compact(strong) in _compact(url)) or any(marker in path for marker in _PRODUCT_MARKERS))


def _general_retail_queries(identity: ProductIdentity) -> list[str]:
    ids = _strong_identifiers(identity) or ([_strong(identity)] if _strong(identity) else [])
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    q = []
    for strong in ids:
        q += [f'"{strong}" precio Perú', f'"{strong}" "S/" Perú', f'"{strong}" tienda Perú', f'"{strong}" comprar Perú']
        if model: q += [f'"{strong}" "{model}" Perú', f'"{model}" "{strong}" {brand} Perú'.strip()]
        q += [f'"{strong}" site:{domain}' for domain in PERU_RETAIL_HINT_DOMAINS]
    return list(dict.fromkeys(x for x in q if x.strip()))


def _general_alias_queries(identity: ProductIdentity) -> list[str]:
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    if not model:
        return []
    queries = [f'"{model}" "{brand}" precio Perú'.strip(), f'"{model}" "{brand}" tienda Perú'.strip()]
    queries += [f'"{model}" "{brand}" site:{domain}'.strip() for domain in PERU_RETAIL_HINT_DOMAINS]
    return list(dict.fromkeys(queries))


def discover_general_peru_retailers(identity: ProductIdentity, *, limit: int = 20) -> list[str]:
    strong = _strong(identity)
    if not strong or limit <= 0: return []
    rows, seen = [], set()
    per_query = max(6, min(20, limit * 2))
    for query in _general_retail_queries(identity):
        try: found = search_web_query(identity, query, limit=per_query, timeout=12)
        except Exception: found = []
        for raw in found:
            url = str(raw or "").strip()
            if not url.startswith(("http://", "https://")) or url in seen: continue
            if not _is_peru_retail_candidate(url, strong): continue
            seen.add(url); rows.append(url)
            if len(rows) >= limit: return rows

    model = str(identity.model or identity.product_name or "").strip()
    if model and len(rows) < limit:
        alias_identity = _alias_identity(identity)
        for query in _general_alias_queries(identity):
            try: found = search_web_query(alias_identity, query, limit=per_query, timeout=12)
            except Exception: found = []
            for raw in found:
                url = str(raw or "").strip()
                if not url.startswith(("http://", "https://")) or url in seen: continue
                if not _is_peru_retail_candidate(url, model): continue
                seen.add(url); rows.append(url)
                if len(rows) >= limit: return rows
    return rows
