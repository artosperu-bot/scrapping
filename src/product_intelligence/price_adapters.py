from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from .models import ProductIdentity
from .price_identity import score_offer_identity
from .price_models import PriceOffer


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _identity_evidence_from_ml(row: dict) -> dict:
    attrs = {str(a.get("id") or "").upper(): a.get("value_name") for a in row.get("attributes", []) if isinstance(a, dict)}
    modelish = attrs.get("MODEL") or attrs.get("MPN") or attrs.get("PART_NUMBER")
    return {
        "mpn": attrs.get("MPN") or attrs.get("PART_NUMBER") or (modelish if modelish and str(modelish).replace("-", "").isalnum() else None),
        "brand": attrs.get("BRAND"),
        "model": attrs.get("MODEL") or row.get("title"),
        "gtin": attrs.get("GTIN") or attrs.get("EAN"),
        "title": row.get("title"),
    }


def parse_mercadolibre_payload(payload: dict, identity: ProductIdentity) -> list[PriceOffer]:
    out: list[PriceOffer] = []
    for row in payload.get("results", []) or []:
        if not isinstance(row, dict):
            continue
        price = _float(row.get("price"))
        if price is None or price <= 0:
            continue
        evidence = _identity_evidence_from_ml(row)
        score, match, conflicts = score_offer_identity(identity, evidence)
        if score < 0.70 or conflicts:
            continue
        seller = row.get("seller") if isinstance(row.get("seller"), dict) else {}
        out.append(PriceOffer(
            part_number=identity.mpn,
            brand=identity.brand,
            model=identity.model or identity.product_name,
            channel="MercadoLibre",
            seller_display_name=seller.get("nickname") or seller.get("seller_name") or (str(row.get("seller_id")) if row.get("seller_id") else None),
            selling_price=price,
            list_price=_float(row.get("original_price")),
            currency=str(row.get("currency_id") or "PEN"),
            stock=_int(row.get("available_quantity")),
            condition=row.get("condition"),
            url=str(row.get("permalink") or ""),
            confidence=score,
            identity_match=match,
            source_type="api",
            source_method="mercadolibre_search",
            publication_id=str(row.get("id") or "") or None,
            evidence=evidence,
        ))
    return out


def _vtex_evidence(product: dict, identity: ProductIdentity) -> dict:
    product_name = str(product.get("productName") or product.get("productTitle") or "")
    declared_model = _first(product.get("Modelo") or product.get("Model") or product.get("model"))
    expected_mpn = _norm(identity.mpn)
    candidates = [declared_model, product_name, product.get("productTitle"), product.get("linkText"), product.get("productReference"), product.get("productReferenceCode")]
    exact_mpn = None
    if expected_mpn:
        for candidate in candidates:
            normalized = _norm(candidate)
            if normalized and expected_mpn in normalized:
                exact_mpn = identity.mpn
                break
    return {
        "mpn": exact_mpn,
        "brand": product.get("brand"),
        "model": declared_model or product_name,
        "title": product_name,
    }


def parse_vtex_payload(payload: list[dict] | dict, identity: ProductIdentity, *, channel: str, source_url: str) -> list[PriceOffer]:
    products = payload if isinstance(payload, list) else [payload]
    out: list[PriceOffer] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        evidence = _vtex_evidence(product, identity)
        score, match, conflicts = score_offer_identity(identity, evidence)
        if score < 0.70 or conflicts:
            continue
        product_url = str(product.get("link") or "").strip()
        product_url = urljoin(source_url.rstrip("/") + "/", product_url) if product_url else source_url
        for item in product.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            sku = str(item.get("itemId") or item.get("referenceId") or "") or None
            for seller in item.get("sellers", []) or []:
                if not isinstance(seller, dict):
                    continue
                offer = seller.get("commertialOffer") or seller.get("commercialOffer") or {}
                price = _float(offer.get("Price"))
                if price is None or price <= 0:
                    continue
                stock = _int(offer.get("AvailableQuantity"))
                is_available = offer.get("IsAvailable")
                available = bool(is_available) if is_available is not None else (stock or 0) > 0
                out.append(PriceOffer(
                    part_number=identity.mpn,
                    brand=identity.brand,
                    model=identity.model or identity.product_name,
                    channel=channel,
                    seller_display_name=seller.get("sellerName") or seller.get("name") or seller.get("sellerId"),
                    selling_price=price,
                    list_price=_float(offer.get("ListPrice")),
                    currency="PEN",
                    stock=stock,
                    availability="available" if available else "unavailable",
                    url=product_url,
                    confidence=score,
                    identity_match=match,
                    source_type="api",
                    source_method="vtex_catalog",
                    publication_id=str(product.get("productId") or "") or None,
                    sku=sku,
                    evidence=evidence,
                ))
    return out
