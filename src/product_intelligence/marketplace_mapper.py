from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import ProductRecord
from .normalize import key_norm


@dataclass
class DerivedValue:
    value: Any = None
    confidence: float = 0.0
    reason: str | None = None


def _clean_text(v: str | None) -> str:
    if not v:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def _identity_is_exact(rec: ProductRecord) -> bool:
    ident = rec.identity
    if ident.match_level == "EXACT":
        return True
    return bool(ident.mpn or ident.ean or ident.upc or ident.gtin) and ident.confidence >= 0.95


def derive_name_en(rec: ProductRecord) -> DerivedValue:
    """Build a conservative English product title from verified identity/specs.

    This is not free-form translation. Technical tokens, brands, models and units are
    preserved. Generic category words are only added when already present in the
    product identity/name, avoiding invented marketing claims.
    """
    i = rec.identity
    # If product_name is already ASCII/technical and contains brand/model, it is safe
    # to reuse as an English logistics name.
    pn = _clean_text(i.product_name)
    if pn:
        norm = key_norm(pn)
        brand_ok = not i.brand or key_norm(i.brand) in norm
        model_ok = not i.model or key_norm(i.model) in norm
        if brand_ok and model_ok:
            return DerivedValue(pn, 0.97 if _identity_is_exact(rec) else 0.90, "verified_product_name")

    parts: list[str] = []
    for v in [i.brand, i.model]:
        v = _clean_text(v)
        if v and key_norm(v) not in {key_norm(x) for x in parts}:
            parts.append(v)

    # Capacity/color are safe variant descriptors when explicitly resolved.
    for v in [i.capacity, i.color]:
        v = _clean_text(v)
        if v and key_norm(v) not in {key_norm(x) for x in parts}:
            parts.append(v)

    # Technical form factor/interface may improve the title without semantic invention.
    for k in ["form_factor", "interface"]:
        spec = rec.specifications.get(k) or {}
        v = _clean_text(spec.get("value"))
        if v and spec.get("confidence", 0) >= 0.90 and key_norm(v) not in {key_norm(x) for x in parts}:
            parts.append(v)

    if len(parts) >= 2:
        return DerivedValue(" ".join(parts), 0.92 if _identity_is_exact(rec) else 0.84, "constructed_from_verified_identity")
    return DerivedValue(None, 0.0, "insufficient_identity")



def derive_product_name(rec: ProductRecord) -> DerivedValue:
    """Marketplace display name from verified identity; no marketing invention."""
    pn = _clean_text(rec.identity.product_name)
    if pn:
        return DerivedValue(pn, 0.98 if _identity_is_exact(rec) else 0.91, "verified_product_name")
    en = derive_name_en(rec)
    if en.value:
        return DerivedValue(en.value, min(en.confidence, 0.93), "constructed_from_verified_identity")
    return DerivedValue(None, 0.0, "insufficient_identity")

def derive_variation(rec: ProductRecord) -> DerivedValue:
    """Return only a defensible marketplace variation value.

    Priority:
    1) explicit resolved variant;
    2) explicit color;
    3) capacity only when product identity is exact and capacity is verified.

    This avoids inventing a variation merely because a product has a specification.
    """
    i = rec.identity
    if i.variant:
        return DerivedValue(_clean_text(i.variant), 0.99, "explicit_identity_variant")
    if i.color:
        return DerivedValue(_clean_text(i.color), 0.96, "explicit_identity_color")
    if i.capacity and _identity_is_exact(rec):
        cap_spec = rec.specifications.get("capacity") or {}
        # Identity capacity itself can be sufficient when tied to exact MPN/EAN/GTIN.
        conf = max(float(cap_spec.get("confidence") or 0), float(i.confidence or 0))
        if conf >= 0.92:
            return DerivedValue(_clean_text(i.capacity), 0.92, "capacity_of_exact_variant")
    return DerivedValue(None, 0.0, "variation_not_proven")


def derive_template_value(rec: ProductRecord, label: str, external_id: str | None = None) -> DerivedValue:
    """General marketplace derivation layer for fields that should not map by fuzzy alias alone."""
    n = key_norm(label)
    if external_id == "39" or n in {"nombre", "name", "product name", "nombre producto", "nombre del producto"}:
        return derive_product_name(rec)
    if external_id == "133816" or n in {"nameen", "name en", "english name", "nombre ingles", "nombre en ingles"}:
        return derive_name_en(rec)
    if external_id == "1700" or "variacion" in n or "variation" in n:
        return derive_variation(rec)
    return DerivedValue(None, 0.0, "no_derivation_rule")


def media_rank(item: dict) -> tuple:
    """Rank validated media without hardcoding brands or domains.

    Exact variant always beats exact product. Within a scope, direct structured media
    and resources carrying strong identity evidence beat generic DOM/network assets.
    Family/unverified resources should not reach auto-fill at all.
    """
    scope_rank = {"EXACT_VARIANT": 4, "EXACT_PRODUCT": 3, "PRODUCT_FAMILY": 1, "UNVERIFIED": 0}
    source = str(item.get("source") or "")
    evidence = set(item.get("evidence") or [])
    source_rank = 0
    if source.startswith("jsonld:Product.image"):
        source_rank = 5
    elif source.startswith("meta:og:image"):
        source_rank = 4
    elif source.startswith("dom:data-zoom-image") or source.startswith("dom:data-large-image"):
        source_rank = 4
    elif source.startswith("dom:srcset") or source.startswith("dom:data-srcset"):
        source_rank = 3
    elif source.startswith("network:image"):
        source_rank = 3
    elif source.startswith("dom:"):
        source_rank = 2

    identity_rank = 0
    if "strong_identifier_in_resource" in evidence:
        identity_rank += 4
    if "capacity_match" in evidence:
        identity_rank += 2
    if any(x.endswith("_match") for x in evidence if x in {"mpn_match", "ean_match", "upc_match", "gtin_match"}):
        identity_rank += 3
    if "triggered_after_variant_selection" in evidence:
        identity_rank += 4

    return (
        scope_rank.get(str(item.get("scope")), 0),
        identity_rank,
        float(item.get("confidence") or 0),
        source_rank,
    )
