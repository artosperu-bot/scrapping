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


@dataclass(frozen=True)
class ConsensusFact:
    value: object
    source_url: str
    authority: str
    identity_status: str
    confidence: float


@dataclass(frozen=True)
class ConsensusDecision:
    accepted_value: object | None
    status: str
    reason: str
    supporting_urls: tuple[str, ...] = ()
    rejected_urls: tuple[str, ...] = ()


def _norm_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _norm_value(value: object) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "").strip().lower())


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


_AUTHORITY_WEIGHT = {
    "manufacturer": 5,
    "official_pdf": 5,
    "manufacturer_support": 4,
    "technical_document": 4,
    "authorized_distributor": 3,
    "technical_database": 3,
    "retailer": 2,
    "third_party": 1,
    "marketplace": 1,
    "unknown": 0,
}


def resolve_evidence_group(facts: list[ConsensusFact]) -> ConsensusDecision:
    """Resolve one semantic value without silently choosing through strong conflicts."""
    usable = [
        fact for fact in facts
        if str(fact.identity_status).upper() in {"EXACT", "COMPATIBLE"}
        and _norm_value(fact.value)
        and float(fact.confidence or 0.0) >= 0.55
    ]
    if not usable:
        return ConsensusDecision(None, "EMPTY", "NO_ELIGIBLE_SOURCE")

    by_value: dict[str, list[ConsensusFact]] = {}
    for fact in usable:
        by_value.setdefault(_norm_value(fact.value), []).append(fact)

    strong_values: dict[str, list[ConsensusFact]] = {}
    for value, rows in by_value.items():
        strong = [
            row for row in rows
            if _AUTHORITY_WEIGHT.get(str(row.authority).lower(), 0) >= 4
            and str(row.identity_status).upper() == "EXACT"
            and float(row.confidence or 0.0) >= 0.85
        ]
        if strong:
            strong_values[value] = strong

    if len(strong_values) > 1:
        rejected = tuple(dict.fromkeys(row.source_url for rows in strong_values.values() for row in rows))
        return ConsensusDecision(None, "CONFLICT", "SOURCE_CONFLICT", (), rejected)

    if len(strong_values) == 1:
        value, rows = next(iter(strong_values.items()))
        representative = max(rows, key=lambda row: (_AUTHORITY_WEIGHT.get(str(row.authority).lower(), 0), row.confidence))
        supporting = tuple(dict.fromkeys(row.source_url for row in rows))
        rejected = tuple(dict.fromkeys(row.source_url for key, other in by_value.items() if key != value for row in other))
        return ConsensusDecision(representative.value, "ACCEPTED", "HIGH_AUTHORITY_EXACT", supporting, rejected)

    ranked_values: list[tuple[int, int, float, str, list[ConsensusFact]]] = []
    for value, rows in by_value.items():
        independent_sources = len({row.source_url for row in rows})
        best_weight = max(_AUTHORITY_WEIGHT.get(str(row.authority).lower(), 0) for row in rows)
        best_confidence = max(float(row.confidence or 0.0) for row in rows)
        ranked_values.append((independent_sources, best_weight, best_confidence, value, rows))
    ranked_values.sort(reverse=True)

    independent_sources, best_weight, best_confidence, value, rows = ranked_values[0]
    if independent_sources < 2 and best_weight < 4:
        return ConsensusDecision(
            None,
            "INSUFFICIENT",
            "INSUFFICIENT_CORROBORATION",
            (),
            tuple(dict.fromkeys(row.source_url for row in rows)),
        )

    competing = [entry for entry in ranked_values[1:] if entry[0] >= independent_sources and entry[1] >= best_weight]
    if competing:
        rejected = tuple(dict.fromkeys(row.source_url for entry in ranked_values for row in entry[4]))
        return ConsensusDecision(None, "CONFLICT", "SOURCE_CONFLICT", (), rejected)

    representative = max(rows, key=lambda row: (_AUTHORITY_WEIGHT.get(str(row.authority).lower(), 0), row.confidence))
    supporting = tuple(dict.fromkeys(row.source_url for row in rows))
    rejected = tuple(dict.fromkeys(row.source_url for entry in ranked_values[1:] for row in entry[4]))
    return ConsensusDecision(representative.value, "ACCEPTED", "CORROBORATED", supporting, rejected)
