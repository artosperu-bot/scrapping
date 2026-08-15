from __future__ import annotations

from dataclasses import dataclass
import re

MATERIAL_PAGE_TYPES = {"PRODUCT", "PRODUCT_VARIANT", "DOCUMENT", "SUPPORT_PRODUCT"}
BLOCKING_IDENTITY = {"CONFLICT", "AMBIGUOUS", "INSUFFICIENT"}

_NOISE_EXACT = {
    "currencycode", "userauthenticated", "customerid", "pageid", "pagetype",
    "taxationpolicy", "analyticsid", "sessionid", "trackingid", "locale",
    "countrycode", "storeid", "userid", "authenticated", "breadcrumb",
}
_NOISE_PREFIXES = ("analytics", "tracking", "session", "customer", "cookie", "taxonomy", "navigation")


@dataclass(frozen=True)
class EvidenceDecision:
    allowed: bool
    reason: str
    confidence: float
    needs_corroboration: bool = False


def _norm_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def is_noise_attribute(attribute: str) -> bool:
    key = _norm_key(attribute)
    return key in _NOISE_EXACT or any(key.startswith(prefix) for prefix in _NOISE_PREFIXES)


def decide_evidence(
    *,
    page_type: str,
    identity_status: str,
    source_class: str,
    extraction_method: str,
    semantic: str,
    confidence: float,
) -> EvidenceDecision:
    page_type = str(page_type or "UNKNOWN").upper()
    identity_status = str(identity_status or "INSUFFICIENT").upper()
    source_class = str(source_class or "unknown").lower()
    method = str(extraction_method or "unknown").lower()
    conf = max(0.0, min(1.0, float(confidence or 0.0)))

    if page_type not in MATERIAL_PAGE_TYPES:
        return EvidenceDecision(False, "PAGE_TYPE_NOT_MATERIAL", conf)
    if identity_status == "CONFLICT":
        return EvidenceDecision(False, "IDENTITY_CONFLICT", conf)
    if identity_status in {"AMBIGUOUS", "INSUFFICIENT"}:
        return EvidenceDecision(False, "IDENTITY_NOT_STRONG_ENOUGH", conf)
    if is_noise_attribute(semantic):
        return EvidenceDecision(False, "NOISE_ATTRIBUTE", conf)

    # Extraction trust floors are deterministic and deliberately conservative.
    if method in {"jsonld", "microdata", "rdfa", "spec_table", "definition_list", "pdf_native"}:
        floor = 0.62
    elif method in {"clean_dom", "main_content"}:
        floor = 0.76
    else:
        floor = 0.84
    if conf < floor:
        return EvidenceDecision(False, "LOW_EXTRACTION_CONFIDENCE", conf)

    high_authority = source_class in {"manufacturer", "manufacturer_support", "official_pdf"}
    if identity_status == "EXACT" and high_authority:
        return EvidenceDecision(True, "ACCEPT_EXACT_HIGH_AUTHORITY", conf, False)

    if source_class in {"marketplace", "third_party", "unknown"}:
        if conf < 0.90:
            return EvidenceDecision(False, "INSUFFICIENT_CORROBORATION", conf, True)
        return EvidenceDecision(True, "ACCEPT_HIGH_CONFIDENCE_LOWER_AUTHORITY", conf, True)

    if identity_status in {"EXACT", "COMPATIBLE"}:
        needs = source_class not in {"manufacturer", "manufacturer_support", "official_pdf", "technical_database"}
        return EvidenceDecision(True, "ACCEPT_POLICY", conf, needs)

    return EvidenceDecision(False, "POLICY_REJECTED", conf)
