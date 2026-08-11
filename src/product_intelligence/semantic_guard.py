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
    syntax_controlled = bool(re.search(r"syntax\s*:\s*(?:one|multiple)\s+value(?:s)?\s+from\s+the\s+list|sintaxis\s*:\s*(?:uno|varios|m[uú]ltiples?)", raw, re.I))

    if field_class == "SELLER_DATA":
        return FieldContract(canonical, "seller", "text", confidence=.98)
    if field_class == "IMAGE":
        return FieldContract("product_image_url", "product", "url", confidence=.99)

    label_n = key_norm(label)
    explicit_package_label = any(x in label_n for x in ["paquete", "package", "packed", "shipping", "peso embalado", "ancho embalado", "largo embalado", "alto embalado"])
    explicit_package_desc = any(x in n for x in ["producto embalado", "packed product", "shipping weight", "gross weight", "peso bruto"])
    outside_package = any(x in n for x in ["fuera de su embalaje", "outside its packaging", "outside the package", "sin embalaje", "without packaging"])
    package = explicit_package_label or (explicit_package_desc and not outside_package)
    context = "package" if package else "product"

    semantic = canonical
    value_type = "controlled" if syntax_controlled else "text"

    # Descriptions are part of the marketplace schema contract. If a machine header is
    # opaque or changes over time, the bilingual instruction still tells us what the
    # field means and which kind of value it expects.
    if not semantic:
        if "bluetooth" in n and any(x in n for x in ["selecciona si", "select whether", "cuenta con", "has bluetooth"]):
            semantic = "bluetooth"; value_type = "controlled"
        elif any(x in n for x in ["resistente al agua", "resistencia al agua", "water resistant", "water resistance"]):
            semantic = "water resistance"; value_type = "controlled"
        elif any(x in n for x in ["tipo de auricular", "type of headphones", "type of headphone"]):
            semantic = "headphone type"; value_type = "controlled"
        elif any(x in n for x in ["autonomia", "autonomía", "battery life", "duracion de la bateria", "duración de la batería"]):
            semantic = "battery_life"; value_type = "duration"
        elif any(x in n for x in ["conectividad", "connectivity"]):
            semantic = "connectivity"; value_type = "controlled"
        elif any(x in n for x in ["numero de serie", "número de serie", "serial number"]):
            semantic = "requires_serial_number"; value_type = "controlled"

    dims: tuple[str, ...] = ()
    forbidden: list[str] = []

    # Canonical or description-inferred meaning wins over incidental words.
    sem = key_norm(semantic or "")
    if c == "power source" or sem == "power source":
        return FieldContract(semantic, context, "controlled", (), (), .98)
    if sem in {"water resistance", "bluetooth", "headphone type", "output type", "features", "connectivity", "requires_serial_number"}:
        return FieldContract(semantic, context, "controlled" if syntax_controlled or sem != "features" else "text", (), (), .98)
    if c in {"package width", "package length", "package height"}:
        return FieldContract(canonical, "package", "dimension", ("length",), (), .99)
    if c == "package weight":
        return FieldContract(canonical, "package", "number", ("mass",), (), .99)

    if c in {"height", "width", "length", "thickness", "dimensions"} or any(x in n for x in [" alto ", " ancho ", " largo ", " altura ", " width ", " height ", " length ", "dimensiones", "dimensions"]):
        value_type = "dimension"; dims = ("length",)
        if not package:
            forbidden += ["cable", "cord", "almohadilla", "ear cushion", "earcup", "ear cup", "diadema", "headband", "package", "paquete", "embalado"]
    elif c == "weight" or "peso" in n or "weight" in n:
        value_type = "number"; dims = ("mass",)
        if not package:
            forbidden += ["package", "paquete", "embalado", "shipping", "gross"]
    elif any(x in n for x in ["potencia", "power", "watts", "watt"]):
        semantic = semantic or "power"; value_type = "number"; dims = ("power",)
    elif sem == "battery_life" or any(x in n for x in ["autonomia", "autonomía", "battery life", "duracion de bateria", "duración de batería"]):
        semantic = semantic or "battery_life"; value_type = "duration"; dims = ("time",); forbidden += ["mah", "wh"]
    elif any(x in n for x in ["frecuencia", "frequency"]):
        value_type = "number"; dims = ("frequency",)
    elif any(x in n for x in ["impedancia", "impedance"]):
        semantic = semantic or "impedance"; value_type = "number"; dims = ("resistance",)
    elif any(x in n for x in ["sensibilidad", "sensitivity"]):
        semantic = semantic or "sensitivity"; value_type = "number"; dims = ("level",)
    elif any(x in n for x in ["capacidad de almacenamiento", "storage capacity"]):
        semantic = "capacity"; value_type = "controlled"; dims = ("data",)
    elif any(x in n for x in ["pais de produccion", "país de producción", "country of production", "country of origin"]):
        semantic = "country_of_origin"; value_type = "controlled"
    elif any(x in n for x in ["codigo de barras", "código de barras", "barcode", "ean", "gtin", "upc"]):
        semantic = semantic or "ean"; value_type = "number"
    elif any(x in n for x in ["serial number", "numero de serie", "número de serie"]):
        semantic = semantic or "requires_serial_number"; value_type = "controlled"
    elif any(x in n for x in ["bluetooth", "resistente al agua", "resistencia al agua", "water resistant", "water resistance"]):
        value_type = "controlled"
    elif any(x in n for x in ["conectividad", "connectivity", "tipo de auricular", "segmento", "tipo de salida", "alimentacion", "alimentación"]):
        value_type = "controlled"
    elif any(x in n for x in ["nameen", "nombre en ingles", "english name"]):
        semantic = "name_en"; context = "logistics"
    elif any(x in n for x in ["namecn", "nombre en chino", "chinese name"]):
        semantic = "name_cn"; context = "logistics"

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
        if not detected and contract.value_type in {"dimension", "duration"}:
            return False, "EXPECTED_UNIT_MISSING", .0
        if detected and not (detected & set(contract.allowed_dimensions)):
            return False, "UNIT_DIMENSION_MISMATCH", .0
        disallowed = detected - set(contract.allowed_dimensions)
        if disallowed and contract.value_type in {"dimension", "duration"}:
            return False, "MIXED_OR_WRONG_UNIT_DIMENSION", .0

    if contract.value_type in {"number", "dimension", "duration"} and not re.search(r"\d", text):
        return False, "NUMERIC_VALUE_MISSING", .0

    return True, "OK", .96
