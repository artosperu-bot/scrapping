from __future__ import annotations

import json
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from .models import Evidence, ProductIdentity
from .structured_extract import extract_embedded_metadata, flatten_pairs
from .image_extract import extract_image_candidates


DOCUMENT_LABELS = [
    "datasheet", "data sheet", "manual", "specification", "spec sheet", "ficha técnica", "ficha tecnica",
    "specs & downloads", "specifications & downloads", "documents & downloads", "downloads",
    "quick start guide", "quickstart guide", "user manual", "declaration of conformity",
    "documentos y descargas", "manual de usuario", "guía de inicio", "guia de inicio",
]


def extract_page(html: str, base_url: str, identity_terms: list[str] | None = None) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    text = soup.get_text("\n", strip=True)
    pdfs = []
    document_links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        label = a.get_text(" ", strip=True).lower()
        is_document_label = any(k in label for k in DOCUMENT_LABELS)
        if ".pdf" in href.lower():
            pdfs.append(href)
        elif is_document_label:
            document_links.append(href)

    jsonld = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            jsonld.append(json.loads(script.string or ""))
        except Exception:
            pass

    embedded = extract_embedded_metadata(html, base_url)
    images = extract_image_candidates(html, base_url, identity_terms=identity_terms)
    return {
        "title": title,
        "text": text,
        "pdfs": list(dict.fromkeys(pdfs)),
        "document_links": list(dict.fromkeys(document_links)),
        "images": images,
        "jsonld": jsonld,
        "embedded": embedded,
    }


def _walk_dicts(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from _walk_dicts(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk_dicts(v)


def identity_from_page(page: dict, expected: ProductIdentity | None = None, source_url: str | None = None) -> ProductIdentity:
    objs = list(_walk_dicts(page.get("jsonld", [])))
    objs += list(_walk_dicts(page.get("embedded", {})))
    prod = next((x for x in objs if str(x.get("@type", x.get("type", ""))).lower().endswith("product")), {})
    brand = prod.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    gtin = prod.get("gtin14") or prod.get("gtin13") or prod.get("gtin12") or prod.get("gtin")
    cand = ProductIdentity(
        brand=brand,
        product_name=prod.get("name") or page.get("title"),
        model=prod.get("model"),
        mpn=prod.get("mpn"),
        sku=prod.get("sku"),
        gtin=str(gtin) if gtin else None,
        ean=str(prod.get("gtin13")) if prod.get("gtin13") else None,
        upc=str(prod.get("gtin12")) if prod.get("gtin12") else None,
    )
    if expected:
        haystack = str(page.get("text") or "").lower()
        compact = re.sub(r"\s+", "", haystack)
        for field in ["mpn", "ean", "upc", "gtin", "model", "brand", "capacity", "variant"]:
            val = getattr(expected, field, None)
            if not val or getattr(cand, field, None):
                continue
            raw = str(val).strip()
            if raw.lower() in haystack or re.sub(r"\s+", "", raw.lower()) in compact:
                setattr(cand, field, raw)
    return cand


def table_evidence(html: str, source_url: str, match_level: str, base_confidence: float, source_type: str = "official_html") -> list[Evidence]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if len(cells) >= 2 and cells[0] and cells[1]:
                out.append(Evidence(
                    attribute=cells[0], raw_value=" | ".join(cells[1:]), normalized_value=" | ".join(cells[1:]),
                    source_url=source_url, source_type=source_type, match_level=match_level, confidence=base_confidence,
                ))
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            out.append(Evidence(
                attribute=dt.get_text(" ", strip=True), raw_value=dd.get_text(" ", strip=True),
                normalized_value=dd.get_text(" ", strip=True), source_url=source_url, source_type=source_type,
                match_level=match_level, confidence=base_confidence,
            ))

    label_classes = re.compile(r"(spec|attribute|feature|label|name|key)", re.I)
    value_classes = re.compile(r"(value|detail|data|content)", re.I)
    for label in soup.find_all(class_=label_classes):
        ltxt = label.get_text(" ", strip=True)
        if not ltxt or len(ltxt) > 100:
            continue
        parent = label.parent
        if not parent:
            continue
        val = parent.find(class_=value_classes)
        if val and val is not label:
            vtxt = val.get_text(" ", strip=True)
            if vtxt and vtxt != ltxt and len(vtxt) <= 500:
                out.append(Evidence(attribute=ltxt, raw_value=vtxt, normalized_value=vtxt, source_url=source_url,
                                    source_type=source_type, match_level=match_level, confidence=max(.55, base_confidence - .08)))
    return out


def structured_evidence(page: dict, source_url: str, match_level: str, confidence: float, source_type: str) -> list[Evidence]:
    out = []
    for path, value in flatten_pairs(page.get("embedded", {})):
        leaf = path.split(".")[-1]
        if leaf.lower() in {"name", "description", "model", "mpn", "sku", "gtin", "gtin12", "gtin13", "gtin14", "brand", "color", "weight", "width", "height", "depth", "material"}:
            out.append(Evidence(attribute=leaf, raw_value=value, normalized_value=value, source_url=source_url,
                                source_type=source_type, selector=f"embedded:{path}", match_level=match_level, confidence=confidence))
    return out
