from __future__ import annotations
import re
from dataclasses import dataclass
from rapidfuzz.fuzz import ratio
from .models import ProductIdentity

EAN_RE = re.compile(r"^\d{13}$")
UPC_RE = re.compile(r"^\d{12}$")
GTIN14_RE = re.compile(r"^\d{14}$")

_CONDITION_PATTERNS = {
    "refurbished": (r"certified[ -]?refurbished", r"\brefurbished\b", r"reacondicionad[oa]"),
    "used": (r"\bused\b", r"\busado\b", r"pre[ -]?owned", r"segunda mano"),
    "open_box": (r"open[ -]?box", r"caja abierta"),
    "renewed": (r"\brenewed\b", r"renovad[oa]"),
}

@dataclass
class IdentityInput:
    value: str
    kind: str | None = None

def detect_identifier(value: str) -> str:
    v = value.strip()
    if EAN_RE.fullmatch(v): return "ean"
    if UPC_RE.fullmatch(v): return "upc"
    if GTIN14_RE.fullmatch(v): return "gtin"
    if re.search(r"[A-Za-z]", v) and re.search(r"\d", v) and len(v) <= 40:
        return "mpn_or_model"
    return "name"

def _norm(v: str | None) -> str:
    if not v: return ""
    return re.sub(r"[^a-z0-9]+", "", v.lower())

def _text_supports(value: str | None, *texts: str | None) -> bool:
    """Conservative lexical support for identity metadata."""
    needle=_norm(value)
    if not needle:
        return False
    haystack=" ".join(_norm(x) for x in texts if x)
    return len(needle) >= 2 and needle in haystack


def _condition_set(*texts: str | None) -> set[str]:
    joined = " ".join(x or "" for x in texts).lower()
    return {
        name
        for name, patterns in _CONDITION_PATTERNS.items()
        if any(re.search(pattern, joined, re.I) for pattern in patterns)
    }


def sanitize_condition_mismatched_identity(expected: ProductIdentity, candidate: ProductIdentity) -> ProductIdentity:
    """Prevent a used/refurbished/open-box listing from redefining a standard product identity.

    Exact MPN/GTIN evidence can still validate the technical product, but commercial condition is
    a separate identity dimension. If the target did not request that condition, condition-bearing
    product names/variants are not promoted to canonical identity metadata.
    """
    expected_conditions = _condition_set(expected.product_name, expected.model, expected.variant)
    candidate_conditions = _condition_set(candidate.product_name, candidate.model, candidate.variant)
    if candidate_conditions - expected_conditions:
        if _condition_set(candidate.product_name) - expected_conditions:
            candidate.product_name = None
        if _condition_set(candidate.variant) - expected_conditions:
            candidate.variant = None
    return candidate


def compare_identity(expected: ProductIdentity, candidate: ProductIdentity) -> ProductIdentity:
    candidate = sanitize_condition_mismatched_identity(expected, candidate)
    confirmed, conflicts = [], []
    score = 0.0
    weights = {"mpn": 0.32, "ean": 0.30, "upc": 0.30, "gtin": 0.30, "model": 0.18,
               "brand": 0.08, "capacity": 0.06, "variant": 0.04, "color": 0.02}
    strong = {"mpn", "ean", "upc", "gtin"}
    strong_match = False
    for field, weight in weights.items():
        a, b = getattr(expected, field, None), getattr(candidate, field, None)
        if not a or not b: continue
        if _norm(str(a)) == _norm(str(b)):
            score += weight; confirmed.append(field)
            if field in strong: strong_match = True
        elif field in strong or field in {"model", "capacity", "variant"}:
            conflicts.append(field)
        elif field == "brand" and expected.brand and candidate.brand:
            conflicts.append(field)

    if not expected.brand and candidate.brand and not _text_supports(
        candidate.brand, candidate.product_name, candidate.model
    ):
        candidate.brand = None

    if conflicts and any(x in strong for x in conflicts):
        level = "CONFLICT"
    elif strong_match and not conflicts:
        level = "EXACT"
    else:
        sim = max(
            ratio(_norm(expected.product_name), _norm(candidate.product_name))/100 if expected.product_name and candidate.product_name else 0,
            ratio(_norm(expected.model), _norm(candidate.model))/100 if expected.model and candidate.model else 0,
        )
        score = min(1.0, score + 0.25 * sim)
        if conflicts: level = "MEDIUM"
        elif score >= .55 or (sim >= .92 and expected.brand and candidate.brand and _norm(expected.brand)==_norm(candidate.brand)): level = "HIGH"
        elif score >= .30 or sim >= .78: level = "MEDIUM"
        else: level = "LOW"
    candidate.confidence = round(min(1.0, score if score else 0.15), 4)
    candidate.match_level = level
    candidate.identifiers_confirmed = sorted(set(confirmed))
    candidate.identifiers_conflicting = sorted(set(conflicts))
    return candidate
