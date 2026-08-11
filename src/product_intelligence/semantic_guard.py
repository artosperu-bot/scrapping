from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any
from .normalize import key_norm


@dataclass
class FieldContract:
    semantic: str | None = None
    context: str = "product"          # product | package | seller | logistics | generic
    value_type: str = "text"          # text | number | boolean | url | controlled | dimension | duration
    allowed_dimensions: tuple[str, ...] = ()
    forbidden_context_tokens: tuple[str, ...] = ()
    confidence: float = 0.7

    def to_dict(self):
        return asdict(self)


# SI-like dimensions used for general sanity checks. This does not try to fully parse units;
# it only blocks obvious cross-attribute contamination.
UNIT_DIMENSIONS = {
    "length": [r"\bmm\b", r"\bcm\b", r"\bm\b", r"\bin\b", r"inch", r"pulg"],
    "mass": [r"\bmg\b", r"\bg\b", r"\bkg\b", r"\blb\b", r"lbs", r"ounce", r"\boz\b"],
    "power": [r"\bmw\b", r"\bw\b", r"watt"],
    "time": [r"\bms\b", r"\bs\b", r"sec", r"second", r"segundo", r"\bmin\b", r"minute", r"hora", r"hour", r"\bh\b"],
    "frequency": [r"\bhz\b", r"khz", r"mhz", r"ghz"],
    "voltage": [r"\bv\b", r"volt"],
    "current": [r"\ba\b", r"amp"],
    "energy": [r"wh", r"kwh"],
    "charge": [r"mah", r"ah"],
    "speed": [r"mb/s", r"gb/s", r"mbps", r"gbps", r"m/s", r"km/h"],
    "temperature": [r"°\s*c", r"\bc\b", r"°\s*f", r"fahrenheit", r"celsius"],
    "resistance": [r"ohm", r"Ω"],
    "level": [r"db", r"dba"],
    "data": [r"\bkb\b", r"\bmb\b", r"\bgb\b", r"\btb\b"],
}

PLACEHOLDER_PATTERNS = [
    r"^\(?\s*(cm|mm|m|kg|g|lb|lbs|h|hz|w|mw)\s*\)?$",
    r"^ej(?:emplo)?\.?\b",
    r"^e\.g\.?\b",
    r"^\. {0,1}\.*$",
    r"^[.\-_]{5,}$",
    r"^esto es un p[aá]rrafo$",
]


def _contains_any(text: str, words: tuple[str, ...] | list[str]) -> bool:
    n = key_norm(text)
    return any(key_norm(w) in n for w in words)


def infer_contract(label: str, description: str | None = None, canonical: str | None = None, field_class: str | None = None) -> FieldContract:
    raw = f"{label} {description or ''}"
    n = key_norm(raw)
    c = key_norm(canonical or "")
    # The template itself is authoritative about controlled vocabularies.
    syntax_controlled = bool(re.search(r"syntax\s*:\s*(?:one|multiple)\s+value(?:s)?\s+from\s+the\s+list|sintaxis\s*:\s*(?:uno|varios|m[uú]ltiples?)", raw, re.I))

    if field_class == "SELLER_DATA":
        return FieldContract(canonical, "seller", "text", confidence=.98)
    if field_class == "IMAGE":
        return FieldContract("product_image_url", "product", "url", confidence=.99)

    # Context first: the FIELD LABEL is authoritative. Descriptions may say
    # "product outside its packaging", which must remain product context.
    label_n = key_norm(label)
    explicit_package_label = any(x in label_n for x in ["paquete", "package", "packed", "shipping", "peso embalado", "ancho embalado", "largo embalado", "alto embalado"])
    explicit_package_desc = any(x in n for x in ["producto embalado", "packed product", "shipping weight", "gross weight", "peso bruto"])
    outside_package = any(x in n for x in ["fuera de su embalaje", "outside its packaging", "outside the package", "sin embalaje", "without packaging"])
    package = explicit_package_label or (explicit_package_desc and not outside_package)
    context = "package" if package else "product"

    semantic = canonical
    value_type = "controlled" if syntax_controlled else "text"
    dims: tuple[str, ...] = ()
    forbidden: list[str] = []

    # Canonical meaning wins over incidental words in verbose marketplace descriptions.
    if c == "power source":
        return FieldContract(canonical, context, "controlled", (), (), .98)
    if c in {"water resistance", "bluetooth", "headphone type", "output type", "features"}:
        return FieldContract(canonical, context, "controlled" if syntax_controlled or c != "features" else "text", (), (), .98)
    if c in {"package width", "package length", "package height"}:
        return FieldContract(canonical, "package", "dimension", ("length",), (), .99)
    if c == "package weight":
        return FieldContract(canonical, "package", "number", ("mass",), (), .99)

    # Generic physical / engineering semantics.
    if c in {"height", "width", "length", "thickness", "dimensions"} or any(x in n for x in [" alto ", " ancho ", " largo ", " altura ", " width ", " height ", " length ", "dimensiones", "dimensions"]):
        value_type = "dimension"
        dims = ("length",)
        if not package:
            forbidden += ["cable", "cord", "almohadilla", "ear cushion", "earcup", "ear cup", "diadema", "headband", "package", "paquete", "embalado"]
    elif c == "weight" or "peso" in n or "weight" in n:
        value_type = "number"
        dims = ("mass",)
        if not package:
            forbidden += ["package", "paquete", "embalado", "shipping", "gross"]
    elif any(x in n for x in ["potencia", "power", "watts", "watt"]):
        semantic = semantic or "power"
        value_type = "number"
        dims = ("power",)
    elif any(x in n for x in ["autonomia", "autonomía", "battery life", "duracion de bateria", "duración de batería"]):
        semantic = semantic or "battery_life"
        value_type = "duration"
        dims = ("time",)
        forbidden += ["mah", "wh"]
    elif any(x in n for x in ["frecuencia", "frequency"]):
        value_type = "number"
        dims = ("frequency",)
    elif any(x in n for x in ["impedancia", "impedance"]):
        semantic = semantic or "impedance"
        value_type = "number"
        dims = ("resistance",)
    elif any(x in n for x in ["sensibilidad", "sensitivity"]):
        semantic = semantic or "sensitivity"
        value_type = "number"
        dims = ("level",)
    elif any(x in n for x in ["capacidad de almacenamiento", "storage capacity"]):
        semantic = "capacity"
        value_type = "controlled"
        dims = ("data",)
    elif any(x in n for x in ["pais de produccion", "país de producción", "country of production", "country of origin"]):
        semantic = "country_of_origin"
        value_type = "controlled"
    elif any(x in n for x in ["codigo de barras", "código de barras", "barcode", "ean", "gtin", "upc"]):
        semantic = semantic or "ean"
        value_type = "number"
    elif any(x in n for x in ["serial number", "numero de serie", "número de serie"]):
        semantic = semantic or "requires_serial_number"
        value_type = "controlled"
    elif any(x in n for x in ["bluetooth", "resistente al agua", "resistencia al agua", "water resistant", "water resistance"]):
        value_type = "controlled"
    elif any(x in n for x in ["conectividad", "connectivity", "tipo de auricular", "segmento", "tipo de salida", "alimentacion", "alimentación"]):
        value_type = "controlled"
    elif any(x in n for x in ["nameen", "nombre en ingles", "english name"]):
        semantic = "name_en"
        context = "logistics"
    elif any(x in n for x in ["namecn", "nombre en chino", "chinese name"]):
        semantic = "name_cn"
        context = "logistics"

    return FieldContract(semantic, context, value_type, dims, tuple(forbidden), .92 if semantic else .72)


def detect_unit_dimensions(value: Any) -> set[str]:
    text = str(value or "").lower()
    found: set[str] = set()
    for dim, pats in UNIT_DIMENSIONS.items():
        if any(re.search(p, text, re.I) for p in pats):
            found.add(dim)
    return found


def is_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    return any(re.search(p, text, re.I) for p in PLACEHOLDER_PATTERNS)


def validate_value(value: Any, contract: FieldContract, *, evidence_attribute: str | None = None, evidence_raw: Any = None) -> tuple[bool, str, float]:
    if value in (None, ""):
        return False, "EMPTY", 0.0
    text = str(value).strip()
    ctx = f"{evidence_attribute or ''} {evidence_raw or ''} {text}"

    if is_placeholder(value):
        return False, "PLACEHOLDER_OR_UNIT_ONLY", 0.0

    if contract.context == "package":
        evidence_n = key_norm(f"{evidence_attribute or ''} {evidence_raw or ''}")
        if not any(t in evidence_n for t in ["package", "packed", "shipping", "gross", "paquete", "embal", "caja", "box", "included", "contenido"]):
            return False, "PACKAGE_CONTEXT_NOT_PROVEN", .0

    if contract.context == "product" and contract.forbidden_context_tokens and _contains_any(ctx, contract.forbidden_context_tokens):
        return False, "WRONG_SUBCOMPONENT_OR_CONTEXT", .0

    detected = detect_unit_dimensions(value)
    if contract.allowed_dimensions:
        # No unit at all can be acceptable for controlled/text fields, but engineering numeric fields require one.
        if not detected and contract.value_type in {"dimension", "duration"}:
            return False, "EXPECTED_UNIT_MISSING", .0
        if detected and not (detected & set(contract.allowed_dimensions)):
            return False, "UNIT_DIMENSION_MISMATCH", .0
        # Explicitly reject common cross dimensions even when another allowed token is present.
        disallowed = detected - set(contract.allowed_dimensions)
        if disallowed and contract.value_type in {"dimension", "duration"}:
            return False, "MIXED_OR_WRONG_UNIT_DIMENSION", .0

    # Basic numeric sanity for fields that should not be prose/labels.
    if contract.value_type in {"number", "dimension", "duration"} and not re.search(r"\d", text):
        return False, "NUMERIC_VALUE_MISSING", .0

    return True, "OK", .96
