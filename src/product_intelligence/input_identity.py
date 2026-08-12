from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .models import ProductIdentity


@dataclass
class ProductQueryEntry:
    identity: ProductIdentity
    source_urls: list[str] = field(default_factory=list)


def _clean(v: str | None) -> str | None:
    v = str(v or "").strip()
    return v or None


def _valid_http_url(value: str | None) -> str | None:
    value = _clean(value)
    if not value:
        return None
    try:
        parsed = urlparse(value)
    except Exception:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def parse_product_entry(line: str) -> ProductQueryEntry | None:
    """Parse one product line with optional source URLs.

    One product identity is enough (MPN/EAN/UPC/GTIN/name). Source URLs are optional,
    may be repeated, and are treated only as priority candidates -- never as trusted
    product evidence until the normal identity validator accepts their content.

    Examples:
      JBLENDURRUN3BTBAM | url=https://www.jbl.com.pe/JBLENDURRUN3BTBAM.html
      name=JBL Tune 530C USB-C | brand=JBL | url=https://www.jbl.com/...
    """
    raw = str(line or "").strip()
    if not raw:
        return None
    parts = [x.strip() for x in raw.split("|") if x.strip()]
    data: dict[str, str] = {}
    source_urls: list[str] = []
    primary = None

    for part in parts:
        um = re.match(r"^(?:url|source|fuente|pagina|página)\s*[:=]\s*(.+)$", part, re.I)
        if um:
            url = _valid_http_url(um.group(1))
            if url and url not in source_urls:
                source_urls.append(url)
            continue

        # Also accept a naked URL as an additional source after the primary identity.
        naked_url = _valid_http_url(part)
        if naked_url:
            if primary is None and not data:
                # URL-only input is intentionally not accepted here: without at least one
                # product identity we cannot safely bind a web page to an Excel row.
                continue
            if naked_url not in source_urls:
                source_urls.append(naked_url)
            continue

        m = re.match(
            r"^(mpn|part(?:\s*number)?|ean|upc|gtin|name|nombre|brand|marca|model|modelo|color|variant|variante)\s*[:=]\s*(.+)$",
            part,
            re.I,
        )
        if not m:
            if primary is None:
                primary = part
            continue
        key = m.group(1).lower().replace(" ", "")
        value = _clean(m.group(2))
        mapping = {
            "part": "mpn",
            "partnumber": "mpn",
            "nombre": "product_name",
            "name": "product_name",
            "marca": "brand",
            "brand": "brand",
            "modelo": "model",
            "model": "model",
            "variante": "variant",
            "variant": "variant",
        }
        data[mapping.get(key, key)] = value

    if primary and not any(data.get(k) for k in ["mpn", "ean", "upc", "gtin", "product_name"]):
        compact = re.sub(r"[\s-]+", "", primary)
        if compact.isdigit() and len(compact) == 12:
            data["upc"] = compact
        elif compact.isdigit() and len(compact) in {8, 13, 14}:
            data["ean" if len(compact) in {8, 13} else "gtin"] = compact
        elif re.fullmatch(r"[A-Za-z0-9._/-]{4,80}", primary) and re.search(r"[A-Za-z]", primary) and re.search(r"\d", primary):
            data["mpn"] = primary
        else:
            data["product_name"] = primary

    if not any(data.get(k) for k in ["mpn", "ean", "upc", "gtin", "product_name"]):
        return None
    allowed = {k: v for k, v in data.items() if k in ProductIdentity.model_fields and v not in (None, "")}
    return ProductQueryEntry(identity=ProductIdentity(**allowed), source_urls=source_urls)


def parse_product_query(line: str) -> ProductIdentity | None:
    """Backward-compatible identity-only parser."""
    entry = parse_product_entry(line)
    return entry.identity if entry else None


def parse_product_entries(text: str) -> list[ProductQueryEntry]:
    out: list[ProductQueryEntry] = []
    seen = set()
    for line in str(text or "").splitlines():
        entry = parse_product_entry(line)
        if not entry:
            continue
        identity = entry.identity
        signature = tuple(
            (k, str(getattr(identity, k, None) or "").lower())
            for k in ["mpn", "ean", "upc", "gtin", "product_name", "brand", "model", "color", "variant"]
        )
        if signature in seen:
            continue
        seen.add(signature)
        out.append(entry)
    return out


def parse_product_queries(text: str) -> list[ProductIdentity]:
    return [entry.identity for entry in parse_product_entries(text)]
