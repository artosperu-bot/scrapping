from __future__ import annotations
import re
from dataclasses import dataclass
from rapidfuzz.fuzz import ratio
from .models import ProductIdentity

EAN_RE = re.compile(r"^\d{13}$")
UPC_RE = re.compile(r"^\d{12}$")
GTIN14_RE = re.compile(r"^\d{14}$")

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
    """Conservative lexical support for identity metadata.

    This prevents an Organization/seller extracted from a commerce page from becoming the
    product brand merely because the page contains the exact MPN. It is deliberately generic:
    a brand/model is considered corroborated when it is present in title/model/name evidence.
    """
    needle=_norm(value)
    if not needle:
        return False
    haystack=" ".join(_norm(x) for x in texts if x)
    return len(needle) >= 2 and needle in haystack

def compare_identity(expected: ProductIdentity, candidate: ProductIdentity) -> ProductIdentity:
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

    # A page may contain an exact MPN while JSON-LD Organization names the seller as brand.
    # When the caller did not already know the brand, do not let an unsupported page-level
    # organization become canonical identity metadata. The later evidence resolver may recover
    # the real product brand from explicit Product.brand/specification evidence.
    if not expected.brand and candidate.brand and not _text_supports(
        candidate.brand, candidate.product_name, candidate.model
    ):
        candidate.brand = None

    if conflicts and any(x in strong for x in conflicts):
        level = "CONFLICT"
    elif strong_match and not conflicts:
        # EXACT means exact product identifier, but confidence remains proportional to the
        # corroboration actually available; it is not automatically 0.9+.
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
