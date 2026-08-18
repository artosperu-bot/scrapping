from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from .identifiers import clean_gtin
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
        "gtin": clean_gtin(attrs.get("GTIN") or attrs.get("EAN") or attrs.get("UPC")),
        "ean": clean_gtin(attrs.get("EAN")),
        "upc": clean_gtin(attrs.get("UPC")),
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
        seller_id = seller.get("id") or row.get("seller_id")
        listing_id = str(row.get("id") or "") or None
        catalog_id = str(row.get("catalog_product_id") or "") or None
        direct_url = str(row.get("permalink") or "")
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
            url=direct_url,
            confidence=score,
            identity_match=match,
            source_type="api",
            source_method="mercadolibre_search",
            publication_id=listing_id,
            seller_id=str(seller_id) if seller_id is not None else None,
            marketplace_product_id=catalog_id,
            marketplace_listing_id=listing_id,
            direct_product_url=direct_url,
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


def _vtex_item_identity_evidence(product_evidence: dict, item: dict, identity: ProductIdentity) -> dict:
    evidence = dict(product_evidence)
    expected = _norm(identity.mpn)
    candidates: list[Any] = [item.get("itemId"), item.get("name"), item.get("nameComplete"), item.get("complementName"), item.get("ean")]
    reference = item.get("referenceId")
    if isinstance(reference, list):
        for entry in reference:
            if isinstance(entry, dict):
                candidates.extend((entry.get("Value"), entry.get("value"), entry.get("Key"), entry.get("key")))
            else:
                candidates.append(entry)
    else:
        candidates.append(reference)
    if expected and any(expected in _norm(candidate) for candidate in candidates if candidate):
        evidence["mpn"] = identity.mpn
    verified = clean_gtin(item.get("ean"))
    if verified:
        evidence["gtin"] = verified
        if len(verified) == 12:
            evidence["upc"] = verified
        elif len(verified) == 13:
            evidence["ean"] = verified
    return evidence


def parse_vtex_payload(payload: list[dict] | dict, identity: ProductIdentity, *, channel: str, source_url: str) -> list[PriceOffer]:
    products = payload if isinstance(payload, list) else [payload]
    out: list[PriceOffer] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        product_evidence = _vtex_evidence(product, identity)
        product_url = str(product.get("link") or "").strip()
        product_url = urljoin(source_url.rstrip("/") + "/", product_url) if product_url else source_url
        for item in product.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            evidence = _vtex_item_identity_evidence(product_evidence, item, identity)
            score, match, conflicts = score_offer_identity(identity, evidence)
            if score < 0.70 or conflicts:
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
                    seller_id=str(seller.get("sellerId") or "") or None,
                    seller_sku=sku,
                    marketplace_product_id=str(product.get("productId") or "") or None,
                    direct_product_url=product_url,
                    evidence=evidence,
                ))
    return out


def _shopify_money(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and any(marker in value for marker in (".", ",")):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    amount = _float(value)
    if amount is None:
        return None
    return amount / 100.0


def parse_shopify_product_payload(
    payload: dict,
    identity: ProductIdentity,
    *,
    channel: str,
    source_url: str,
) -> list[PriceOffer]:
    """Parse Shopify's public product JSON endpoint using exact SKU/barcode evidence."""
    if not isinstance(payload, dict):
        return []
    title = str(payload.get("title") or "").strip()
    vendor = str(payload.get("vendor") or "").strip() or None
    expected_mpn = _norm(identity.mpn)
    out: list[PriceOffer] = []
    for variant in payload.get("variants", []) or []:
        if not isinstance(variant, dict):
            continue
        sku = str(variant.get("sku") or "").strip()
        barcode = str(variant.get("barcode") or "").strip()
        verified_barcode = clean_gtin(barcode)
        evidence = {
            "mpn": identity.mpn if expected_mpn and _norm(sku) == expected_mpn else None,
            "gtin": verified_barcode,
            "upc": verified_barcode if verified_barcode and len(verified_barcode) == 12 else None,
            "ean": verified_barcode if verified_barcode and len(verified_barcode) == 13 else None,
            "brand": vendor,
            "model": title,
            "title": title,
        }
        score, match, conflicts = score_offer_identity(identity, evidence)
        if score < 0.70 or conflicts:
            continue
        price = _shopify_money(variant.get("price"))
        if price is None or price <= 0:
            continue
        compare = _shopify_money(variant.get("compare_at_price"))
        available = variant.get("available")
        out.append(PriceOffer(
            part_number=identity.mpn,
            brand=identity.brand,
            model=identity.model or identity.product_name,
            channel=channel,
            seller_display_name=channel,
            selling_price=price,
            list_price=compare if compare and compare >= price else None,
            currency="PEN",
            availability=("available" if available else "unavailable") if available is not None else None,
            url=source_url,
            confidence=score,
            identity_match=match,
            source_type="api",
            source_method="shopify_product_json",
            publication_id=str(payload.get("id") or "") or None,
            sku=sku or (str(variant.get("id") or "") or None),
            seller_sku=sku or None,
            internal_product_id=str(payload.get("id") or "") or None,
            direct_product_url=source_url,
            evidence=evidence,
        ))
    return out
