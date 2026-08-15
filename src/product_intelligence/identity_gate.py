from __future__ import annotations

from dataclasses import dataclass
import re

from .models import ProductIdentity


@dataclass(frozen=True)
class ObservedIdentity:
    brand: str | None = None
    model: str | None = None
    product_name: str | None = None
    mpns: tuple[str, ...] = ()
    gtins: tuple[str, ...] = ()
    eans: tuple[str, ...] = ()
    upcs: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdentityAssessment:
    status: str
    confidence: float
    reasons: tuple[str, ...]
    matched_identifiers: tuple[str, ...] = ()
    conflicting_identifiers: tuple[str, ...] = ()


def _norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _tokens(value: str | None) -> tuple[str, ...]:
    return tuple(x for x in re.split(r"[^a-z0-9]+", str(value or "").lower()) if len(x) >= 2)


def _requested_strong(requested: ProductIdentity) -> dict[str, str]:
    return {
        key: _norm(getattr(requested, key, None))
        for key in ("mpn", "gtin", "ean", "upc")
        if _norm(getattr(requested, key, None))
    }


def _observed_strong(observed: ObservedIdentity) -> dict[str, set[str]]:
    return {
        "mpn": {_norm(x) for x in observed.mpns if _norm(x)},
        "gtin": {_norm(x) for x in observed.gtins if _norm(x)},
        "ean": {_norm(x) for x in observed.eans if _norm(x)},
        "upc": {_norm(x) for x in observed.upcs if _norm(x)},
    }


def assess_identity(requested: ProductIdentity, observed: ObservedIdentity) -> IdentityAssessment:
    requested_ids = _requested_strong(requested)
    observed_ids = _observed_strong(observed)
    matched: list[str] = []
    conflicts: list[str] = []

    for kind, req in requested_ids.items():
        vals = observed_ids.get(kind, set())
        if not vals:
            continue
        if req in vals:
            matched.append(f"{kind.upper()}:{req}")
            different = vals - {req}
            if different:
                conflicts.extend(f"{kind.upper()}:{x}" for x in sorted(different))
        else:
            conflicts.extend(f"{kind.upper()}:{x}" for x in sorted(vals))

    # A requested strong identifier must not be contradicted by an observed identifier
    # of the same family. A different observed MPN is a hard conflict.
    if conflicts:
        return IdentityAssessment(
            status="CONFLICT",
            confidence=0.99,
            reasons=("STRONG_IDENTIFIER_CONFLICT",),
            matched_identifiers=tuple(matched),
            conflicting_identifiers=tuple(conflicts),
        )
    if matched:
        return IdentityAssessment(
            status="EXACT",
            confidence=0.99,
            reasons=("STRONG_IDENTIFIER_MATCH",),
            matched_identifiers=tuple(matched),
        )

    req_brand = _norm(requested.brand)
    obs_brand = _norm(observed.brand)
    if req_brand and obs_brand and req_brand != obs_brand:
        return IdentityAssessment("CONFLICT", 0.96, ("BRAND_CONFLICT",))

    req_model = _norm(requested.model or requested.product_name)
    obs_model = _norm(observed.model or observed.product_name)
    if req_model and obs_model:
        if req_model == obs_model:
            return IdentityAssessment("COMPATIBLE", 0.92, ("EXACT_MODEL_MATCH",))

        req_tokens = set(_tokens(requested.model or requested.product_name))
        obs_tokens = set(_tokens(observed.model or observed.product_name))
        shared = req_tokens & obs_tokens
        # Same brand but a clearly different dominant model is a hard conflict.
        if req_brand and (not obs_brand or req_brand == obs_brand):
            if req_tokens and obs_tokens and len(shared) < max(1, min(len(req_tokens), len(obs_tokens)) // 2):
                return IdentityAssessment("CONFLICT", 0.94, ("DOMINANT_MODEL_CONFLICT",))
            return IdentityAssessment("AMBIGUOUS", 0.60, ("MODEL_FAMILY_OVERLAP_ONLY",))

    if requested_ids and any(observed_ids.values()):
        # Different identifier kinds without a comparable requested value are useful hints,
        # but cannot prove exact identity by themselves.
        return IdentityAssessment("AMBIGUOUS", 0.58, ("UNALIGNED_STRONG_IDENTIFIERS",))

    if req_brand and obs_brand and req_brand == obs_brand and obs_model:
        return IdentityAssessment("AMBIGUOUS", 0.55, ("BRAND_ONLY_WITH_DIFFERENT_MODEL_SIGNAL",))

    return IdentityAssessment("INSUFFICIENT", 0.25, ("INSUFFICIENT_PRODUCT_IDENTITY_SIGNALS",))
