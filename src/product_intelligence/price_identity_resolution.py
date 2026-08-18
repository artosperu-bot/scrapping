from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .identity_bootstrap import _brand_candidate_quality, bootstrap_identity
from .models import ProductIdentity


@dataclass(slots=True)
class PriceIdentityResolution:
    input_identity: ProductIdentity
    identity: ProductIdentity
    status: str
    confidence: float = 0.0
    reason: str = ""
    evidence_backed: bool = False
    official_domain_hint: str | None = None
    candidate_urls: list[str] = field(default_factory=list)
    page_signals: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "confidence": self.confidence,
            "reason": self.reason,
            "evidence_backed": self.evidence_backed,
            "official_domain_hint": self.official_domain_hint,
            "input_identity": self.input_identity.model_dump(),
            "resolved_identity": self.identity.model_dump(),
            "candidate_urls": list(self.candidate_urls),
            "page_signals": list(self.page_signals),
            "error": self.error,
        }


def _raw(identity: ProductIdentity) -> str:
    return str(
        identity.mpn or identity.ean or identity.upc or identity.gtin or identity.sku
        or identity.model or identity.product_name or ""
    ).strip()


def _evidence_backed(result: Any) -> bool:
    if str(getattr(result, "official_domain_hint", "") or "").strip():
        return True
    if int(getattr(result, "page_probes_succeeded", 0) or 0) > 0:
        return True
    hosts = getattr(result, "brand_hosts", {}) or {}
    return any(int(value or 0) >= 2 for value in hosts.values())


def resolve_price_identity(
    identity: ProductIdentity,
    *,
    bootstrap: Callable[..., Any] = bootstrap_identity,
    timeout: int = 8,
    limit_per_query: int = 18,
) -> PriceIdentityResolution:
    """Resolve partial product identity before price discovery without making it mandatory.

    The existing bootstrap remains the authority for evidence collection. This bridge
    only accepts a resolved brand when the result is evidence-backed and passes the
    generic/category brand guard. Any failure returns the original input unchanged.
    """
    original = identity.model_copy(deep=True)
    raw = _raw(original)
    if not raw:
        return PriceIdentityResolution(original, original.model_copy(deep=True), "FALLBACK_ORIGINAL", reason="NO_RAW_IDENTITY")
    try:
        result = bootstrap(original.model_copy(deep=True), timeout=timeout, limit_per_query=limit_per_query)
    except Exception as exc:
        return PriceIdentityResolution(
            original,
            original.model_copy(deep=True),
            "FALLBACK_ORIGINAL",
            reason="RESOLVER_ERROR",
            error=type(exc).__name__,
        )

    resolved = getattr(result, "identity", None)
    status = str(getattr(result, "status", "") or "")
    confidence = float(getattr(result, "confidence", 0.0) or 0.0)
    reason = str(getattr(result, "reason", "") or "")
    backed = _evidence_backed(result)
    brand = str(getattr(resolved, "brand", "") or getattr(resolved, "manufacturer", "") or "").strip() if resolved else ""

    common = {
        "confidence": confidence,
        "reason": reason,
        "evidence_backed": backed,
        "official_domain_hint": getattr(result, "official_domain_hint", None),
        "candidate_urls": list(getattr(result, "candidate_urls", []) or []),
        "page_signals": list(getattr(result, "page_signals", []) or []),
    }

    if status != "RESOLVED" or resolved is None:
        return PriceIdentityResolution(original, original.model_copy(deep=True), "FALLBACK_ORIGINAL", **common)

    if brand and not _brand_candidate_quality(brand, raw):
        return PriceIdentityResolution(original, original.model_copy(deep=True), "REJECTED_RESOLUTION", **common)

    # A caller-provided brand/model is already explicit identity and does not need
    # web corroboration. Newly learned brand identity must have independent evidence.
    learned_brand = bool(brand and not (original.brand or original.manufacturer))
    if learned_brand and not backed:
        return PriceIdentityResolution(original, original.model_copy(deep=True), "REJECTED_RESOLUTION", **common)

    return PriceIdentityResolution(original, resolved.model_copy(deep=True), "RESOLVED", **common)
