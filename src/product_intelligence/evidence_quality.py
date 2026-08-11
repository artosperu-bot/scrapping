from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from .models import Evidence
from .normalize import key_norm

# Generic UI/navigation noise. These are not product rules; they are page-chrome rules.
NOISE_PATTERNS = [
    r"subscription\s+email", r"ingresa\s+tu\s+correo", r"newsletter", r"cookie(s)?\b",
    r"why\s+buy\s+direct", r"buy\s+authentic", r"privacy\s+policy", r"terms\s+(of|and)\s+use",
    r"add\s+to\s+cart", r"shopping\s+cart", r"sign\s+in", r"log\s+in", r"close\s*$",
    r"footer[-_ ]?logo", r"harman\s+logo", r"mark\s+levinson", r"lexicon", r"revel",
]

CONTROL_ONLY = re.compile(r"^[\x00-\x1f\x7f\s]+$")

# Canonicals whose semantics are too specific to be selected from a generic word alone.
STRICT_ATTRIBUTE_HINTS = {
    "endurance_tbw": (r"\btbw\b", r"total\s+bytes\s+written", r"bytes\s+written"),
    "technical_support": (r"technical\s+support", r"soporte\s+t[eé]cnico"),
    "battery_life": (r"battery\s+life", r"play\s*time", r"talk\s*time", r"autonom", r"duraci[oó]n\s+de\s+bater"),
    "package_contents": (r"package\s+contents", r"what.?s\s+in\s+the\s+box", r"contenido\s+del\s+paquete", r"contenido\s+de\s+la\s+caja"),
}


def _clean(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).replace("\u00a0", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def is_noise_text(text: Any) -> bool:
    s = _clean(text)
    if not s:
        return True
    if CONTROL_ONLY.match(s):
        return True
    low = key_norm(s)
    if len(s) > 500 and not re.search(r"\d", s):
        return True
    return any(re.search(p, low, re.I) for p in NOISE_PATTERNS)


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
    if sel in {"line_prefix", "next_line"}:
        q -= 0.10 if sel == "line_prefix" else 0.16
    if "secondary" in st or "marketplace" in st:
        q -= 0.10
    return max(0.0, min(1.0, q))


def generic_evidence_gate(ev: Evidence) -> tuple[bool, str, float]:
    attr = _clean(ev.attribute)
    value = _clean(ev.normalized_value if ev.normalized_value is not None else ev.raw_value)
    if not attr or is_noise_text(attr):
        return False, "ATTRIBUTE_NOISE", 0.0
    if not value or is_noise_text(value):
        return False, "VALUE_NOISE_OR_EMPTY", 0.0
    if len(attr) > 140:
        return False, "ATTRIBUTE_TOO_LONG", 0.0
    if value in {"-", "–", "—", ":", "/"}:
        return False, "VALUE_PUNCTUATION_ONLY", 0.0

    # Control characters or OCR junk should never win a field.
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value):
        return False, "CONTROL_CHARACTER_NOISE", 0.0

    q = source_quality(ev)
    q *= float(ev.confidence or 0.0)
    if q < 0.35:
        return False, "LOW_EVIDENCE_QUALITY", q
    return True, "OK", q


def strict_semantic_gate(canonical: str | None, ev: Evidence) -> tuple[bool, str]:
    """Reject known ambiguous mappings unless the evidence itself proves the meaning."""
    if not canonical:
        return True, "NO_CANONICAL"
    attr = key_norm(_clean(ev.attribute))
    value = key_norm(_clean(ev.normalized_value if ev.normalized_value is not None else ev.raw_value))
    joined = f"{attr} {value}"

    hints = STRICT_ATTRIBUTE_HINTS.get(canonical)
    if hints and not any(re.search(p, joined, re.I) for p in hints):
        return False, f"STRICT_SEMANTIC_NOT_PROVEN:{canonical}"

    if canonical == "endurance_tbw":
        if not (re.search(r"\btbw\b", value, re.I) or re.search(r"\d+(?:[.,]\d+)?\s*tbw\b", value, re.I)):
            return False, "TBW_UNIT_OR_LABEL_MISSING"
    if canonical == "battery_life":
        if not (re.search(r"\d", value) and re.search(r"\b(h|hr|hrs|hour|hours|hora|horas|min|minutes?)\b", value, re.I)):
            return False, "BATTERY_LIFE_DURATION_MISSING"
    if canonical == "weight":
        if not re.search(r"\d", value) or not re.search(r"\b(mg|g|kg|lb|lbs|oz)\b", value, re.I):
            return False, "WEIGHT_UNIT_MISSING"
    if canonical == "dimensions":
        # Whole-product dimensions require at least 2 dimensions, not a label such as 'Peso (g)'.
        count = len(re.findall(r"\d+(?:[.,]\d+)?\s*(?:mm|cm|m|in|inch|pulg)", value, re.I))
        if count < 2:
            return False, "DIMENSION_VECTOR_NOT_PROVEN"
    if canonical == "power":
        # Audio/electrical power is watts. m/s, dBm, 5V1A, etc. must not map here.
        if not re.search(r"\d+(?:[.,]\d+)?\s*(?:m?w|watt)", value, re.I):
            return False, "POWER_WATT_UNIT_MISSING"
    if canonical == "package_contents":
        # Reject marketing prose as box contents. Prefer list-ish or explicit package labels.
        explicit = re.search(r"package|box|contenido|incluye|included|in the box", attr, re.I)
        listish = bool(re.search(r"(^|[,;])\s*\d+\s*(?:x|×)?\s+", value, re.I)) or bool(re.search(r"[,;]", value))
        if not explicit or not listish:
            return False, "PACKAGE_CONTENTS_NOT_EXPLICIT"
    if canonical == "warranty":
        # Marketplace product warranty asks for actual time/conditions; vague labels like
        # "factory" are not enough to upload.
        if not (re.search(r"\d+\s*(?:month|months|mes|meses|year|years|año|años)", value, re.I) or re.search(r"limited warranty|garant[ií]a limitada", value, re.I)):
            return False, "WARRANTY_TERMS_NOT_PROVEN"
    if canonical == "technical_support":
        if not re.search(r"technical\s+support|soporte\s+t[eé]cnico", joined, re.I):
            return False, "TECHNICAL_SUPPORT_NOT_EXPLICIT"
    if canonical == "brand" and len(value) > 60:
        return False, "BRAND_VALUE_IMPLAUSIBLE"
    return True, "OK"
