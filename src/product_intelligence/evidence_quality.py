from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from .models import Evidence
from .normalize import key_norm

NOISE_PATTERNS = [
    r"subscription\s+email", r"ingresa\s+tu\s+correo", r"newsletter", r"cookie(s)?\b",
    r"why\s+buy\s+direct", r"buy\s+authentic", r"privacy\s+policy", r"terms\s+(of|and)\s+use",
    r"add\s+to\s+cart", r"shopping\s+cart", r"sign\s+in", r"log\s+in", r"close\s*$",
    r"footer[-_ ]?logo", r"harman\s+logo", r"mark\s+levinson", r"lexicon", r"revel",
]

CONTROL_ONLY = re.compile(r"^[\x00-\x1f\x7f\s]+$")

STRICT_ATTRIBUTE_HINTS = {
    "endurance_tbw": (r"\btbw\b", r"total\s+bytes\s+written", r"bytes\s+written"),
    "technical_support": (r"technical\s+support", r"soporte\s+t[eé]cnico"),
    "battery_life": (r"battery\s+life", r"play\s*time", r"talk\s*time", r"autonom", r"duraci[oó]n\s+de\s+bater"),
    "package_contents": (r"package\s+contents", r"what.?s\s+in\s+the\s+box", r"contenido\s+del\s+paquete", r"contenido\s+de\s+la\s+caja"),
}

LABEL_ONLY_VALUES = {
    "version", "enabled", "disabled", "de audio", "de pc", "del dial",
    "info", "information", "chart", "(lbs)", "lbs", "(approximate)", "approximate",
}


def _clean(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).replace("\u00a0", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _base_noise(text: Any) -> bool:
    s=_clean(text)
    if not s or CONTROL_ONLY.match(s):
        return True
    low=key_norm(s)
    if len(s)>500 and not re.search(r"\d",s):
        return True
    return any(re.search(p,low,re.I) for p in NOISE_PATTERNS)


def is_noise_text(text: Any) -> bool:
    return _base_noise(text)


def is_noise_value(text: Any) -> bool:
    if _base_noise(text):
        return True
    return key_norm(_clean(text)) in LABEL_ONLY_VALUES


def source_quality(ev: Evidence) -> float:
    st = (ev.source_type or "").lower()
    sel = (ev.selector or "").lower()
    q = 0.72
    if "official" in st:
        q += 0.10
    if "json" in st or "structured" in st:
        q += 0.08
    if "pdf" in st:
        q += 0.05
    if "microdata" in sel or "json-ld" in sel:
        q += 0.08
    if sel in {"line_prefix", "next_line", "target_next_line"}:
        q -= 0.10 if sel == "line_prefix" else 0.16
    if "secondary" in st or "marketplace" in st:
        q -= 0.10
    return max(0.0, min(1.0, q))


def generic_evidence_gate(ev: Evidence) -> tuple[bool, str, float]:
    attr = _clean(ev.attribute)
    value = _clean(ev.normalized_value if ev.normalized_value is not None else ev.raw_value)
    if not attr or is_noise_text(attr):
        return False, "ATTRIBUTE_NOISE", 0.0
    if not value or is_noise_value(value):
        return False, "VALUE_NOISE_OR_EMPTY", 0.0
    if len(attr) > 140:
        return False, "ATTRIBUTE_TOO_LONG", 0.0
    if value in {"-", "–", "—", ":", "/"}:
        return False, "VALUE_PUNCTUATION_ONLY", 0.0
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value):
        return False, "CONTROL_CHARACTER_NOISE", 0.0

    q = source_quality(ev)
    q *= float(ev.confidence or 0.0)
    if q < 0.35:
        return False, "LOW_EVIDENCE_QUALITY", q
    return True, "OK", q


def strict_semantic_gate(canonical: str | None, ev: Evidence) -> tuple[bool, str]:
    if not canonical:
        return True, "NO_CANONICAL"
    attr = key_norm(_clean(ev.attribute))
    raw_value = _clean(ev.normalized_value if ev.normalized_value is not None else ev.raw_value)
    value = key_norm(raw_value)
    joined = f"{attr} {value}"
    selector = key_norm(_clean(ev.selector))

    # Never let media metadata (pixel width/height, gallery dimensions, etc.) become
    # physical product/package dimensions. This is a source-path semantic mismatch.
    if canonical in {"width", "height", "length", "dimensions", "package_width", "package_height", "package_length"}:
        if re.search(r"(?:image|images|img|media|gallery|picture|photo).*(?:width|height|size|dimension)|(?:width|height).*(?:image|images|img|media|gallery)", selector, re.I):
            return False, "MEDIA_DIMENSION_NOT_PHYSICAL_DIMENSION"

    hints = STRICT_ATTRIBUTE_HINTS.get(canonical)
    if hints and not any(re.search(p, joined, re.I) for p in hints):
        return False, f"STRICT_SEMANTIC_NOT_PROVEN:{canonical}"

    if canonical == "endurance_tbw":
        if not (re.search(r"\btbw\b", value, re.I) or re.search(r"\d+(?:[.,]\d+)?\s*tbw\b", value, re.I)):
            return False, "TBW_UNIT_OR_LABEL_MISSING"
    if canonical == "battery_life":
        if not (re.search(r"\d", value) and re.search(r"\b(h|hr|hrs|hour|hours|hora|horas|min|minutes?)\b", value, re.I)):
            return False, "BATTERY_LIFE_DURATION_MISSING"
    if canonical in {"weight", "package_weight"}:
        if not re.search(r"\d", value) or not re.search(r"\b(mg|g|kg|lb|lbs|oz)\b", value, re.I):
            return False, "WEIGHT_UNIT_MISSING"
    if canonical in {"width", "height", "length", "package_width", "package_height", "package_length"}:
        if not re.search(r"\d", value):
            return False, "DIMENSION_NUMBER_MISSING"
        if not re.search(r"\b(mm|cm|m|in|inch|inches|pulg|pulgada|pulgadas)\b|\"", raw_value, re.I):
            return False, "DIMENSION_UNIT_MISSING"
    if canonical == "dimensions":
        count = len(re.findall(r"\d+(?:[.,]\d+)?\s*(?:mm|cm|m|in|inch|pulg)", value, re.I))
        if count < 2:
            return False, "DIMENSION_VECTOR_NOT_PROVEN"
    if canonical == "power":
        if not re.search(r"\d+(?:[.,]\d+)?\s*(?:m?w|watt)", value, re.I):
            return False, "POWER_WATT_UNIT_MISSING"
    if canonical == "package_contents":
        explicit = re.search(r"package|box|contenido|incluye|included|in the box", attr, re.I)
        listish = bool(re.search(r"(^|[,;])\s*\d+\s*(?:x|×)?\s+", value, re.I)) or bool(re.search(r"[,;]", value))
        if not explicit or not listish:
            return False, "PACKAGE_CONTENTS_NOT_EXPLICIT"
    if canonical == "warranty":
        if not (re.search(r"\d+\s*(?:month|months|mes|meses|year|years|año|años)", value, re.I) or re.search(r"limited warranty|garant[ií]a limitada", value, re.I)):
            return False, "WARRANTY_TERMS_NOT_PROVEN"
    if canonical == "technical_support":
        if not re.search(r"technical\s+support|soporte\s+t[eé]cnico", joined, re.I):
            return False, "TECHNICAL_SUPPORT_NOT_EXPLICIT"
    if canonical == "brand":
        if len(raw_value) > 60:
            return False, "BRAND_VALUE_IMPLAUSIBLE"
        if value in {"manufacturer", "fabricante", "seller", "merchant", "distributor", "distribuidor", "info", "information"}:
            return False, "BRAND_LABEL_NOT_VALUE"
    if canonical == "processor":
        if value in {"de pc", "pc", "procesador", "processor", "cpu", "chipset"} or len(value) < 3:
            return False, "PROCESSOR_VALUE_IMPLAUSIBLE"
        if not (re.search(r"\d", raw_value) or re.search(r"intel|amd|ryzen|core|snapdragon|mediatek|apple|exynos|unisoc|celeron|pentium", value, re.I)):
            return False, "PROCESSOR_MODEL_NOT_PROVEN"
    if canonical == "bluetooth":
        if value in {"version", "enabled", "disabled", "bluetooth version", "version bluetooth", "version de bluetooth"}:
            return False, "BLUETOOTH_LABEL_NOT_VALUE"
        if re.search(r"version", attr, re.I) and not re.search(r"\b(?:bluetooth\s*)?\d(?:\.\d)?\b", raw_value, re.I):
            return False, "BLUETOOTH_VERSION_FORMAT_INVALID"
        if re.search(r"power|signal|frequency|frecuencia|transmitter|transmisor|dbm|mw", attr, re.I):
            return False, "BLUETOOTH_TELEMETRY_NOT_TRANSPORT"
    if canonical == "color":
        if value in {"del dial", "dial", "color", "colour", "variant", "variante"}:
            return False, "COLOR_VALUE_IMPLAUSIBLE"
        if re.match(r"^(de|del|para|con)\b", value):
            return False, "COLOR_FRAGMENT_REJECTED"
    if canonical == "interface":
        if value in {"de audio", "audio", "interface", "interfaz", "conexion", "conectividad"}:
            return False, "INTERFACE_LABEL_NOT_VALUE"
    return True, "OK"
