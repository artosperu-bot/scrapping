from __future__ import annotations

from dataclasses import dataclass
import re

from .final_evidence_gate import is_sku_sensitive_field


IDENTIFIER = "IDENTIFIER"
SKU_VARIANT = "SKU_VARIANT"
TECHNICAL = "TECHNICAL"
WARRANTY_REGIONAL = "WARRANTY_REGIONAL"
PACKAGE = "PACKAGE"
COMPATIBILITY = "COMPATIBILITY"
GENERAL = "GENERAL"

CORE = "CORE"
IMPORTANT = "IMPORTANT"
OPTIONAL = "OPTIONAL"


@dataclass(frozen=True)
class FieldPlan:
    field: str
    field_kind: str
    required_scope: str
    priority: str
    preferred_source_kinds: tuple[str, ...]


def _norm(value: str | None) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[_-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def plan_field(field: str, *, required: bool = True) -> FieldPlan:
    name = str(field or "").strip()
    normalized = _norm(name)

    identifier_terms = (
        "gtin", "ean", "upc", "barcode", "mpn", "manufacturer part number",
        "manufacturer sku", "sku", "part number",
    )
    warranty_terms = ("warranty", "garantia", "garantía")
    package_terms = (
        "package", "packaging", "box contents", "package contents", "contenido del paquete",
        "included accessories", "accesorios incluidos", "shipping weight", "package weight",
    )
    compatibility_terms = (
        "compatibility", "compatible", "compatibilidad", "supported device", "supported os",
    )
    technical_terms = (
        "driver", "battery", "bateria", "batería", "processor", "cpu", "display", "screen",
        "frequency", "hz", "bluetooth", "wifi", "wi fi", "protocol", "port", "usb",
        "dimension", "weight", "peso", "power", "potencia", "voltage", "resolution",
        "water", "ip rating", "charging", "autonomy", "autonomia", "runtime", "memory technology",
    )

    if normalized in {"brand", "marca", "model", "modelo", "product name", "product_name"}:
        return FieldPlan(name, IDENTIFIER, "MODEL", CORE, ("EXISTING_IDENTIFIERS", "MANUFACTURER", "PRODUCT_CONTENT"))

    if _contains(normalized, identifier_terms):
        return FieldPlan(name, IDENTIFIER, "SKU", CORE, ("EXISTING_IDENTIFIERS", "IDENTITY_RESOLVER", "MANUFACTURER", "PRODUCT_CONTENT", "AUTHORIZED_DISTRIBUTOR"))

    if _contains(normalized, warranty_terms):
        return FieldPlan(name, WARRANTY_REGIONAL, "SKU", IMPORTANT if required else OPTIONAL, ("MANUFACTURER_SUPPORT", "MANUFACTURER", "AUTHORIZED_DISTRIBUTOR"))

    if _contains(normalized, package_terms):
        return FieldPlan(name, PACKAGE, "SKU", IMPORTANT if required else OPTIONAL, ("MANUFACTURER", "AUTHORIZED_DISTRIBUTOR", "PRODUCT_CONTENT"))

    if _contains(normalized, compatibility_terms):
        return FieldPlan(name, COMPATIBILITY, "MODEL", IMPORTANT if required else OPTIONAL, ("MANUFACTURER_SUPPORT", "OFFICIAL_PDF", "MANUFACTURER"))

    if is_sku_sensitive_field(normalized):
        return FieldPlan(name, SKU_VARIANT, "SKU", IMPORTANT if required else OPTIONAL, ("MANUFACTURER", "PRODUCT_CONTENT", "AUTHORIZED_DISTRIBUTOR"))

    if _contains(normalized, technical_terms):
        return FieldPlan(name, TECHNICAL, "MODEL", IMPORTANT if required else OPTIONAL, ("OFFICIAL_PDF", "MANUFACTURER", "MANUFACTURER_SUPPORT", "PRODUCT_CONTENT"))

    return FieldPlan(name, GENERAL, "MODEL", IMPORTANT if required else OPTIONAL, ("MANUFACTURER", "OFFICIAL_PDF", "PRODUCT_CONTENT", "AUTHORIZED_DISTRIBUTOR"))


def plan_fields(fields) -> tuple[FieldPlan, ...]:
    seen: set[str] = set()
    plans: list[FieldPlan] = []
    for field in fields or ():
        text = str(field or "").strip()
        key = _norm(text)
        if not text or key in seen:
            continue
        seen.add(key)
        plans.append(plan_field(text))
    return tuple(plans)
