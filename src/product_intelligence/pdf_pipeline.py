from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import document_discovery as core_discovery
from .document_discovery import classify_document_candidate
from .identity_refinement import (
    brand_sanity_pass,
    identity_sanity_pass,
    model_sanity_pass,
    refine_code_identity,
)
from .models import ProductIdentity
from .normalize import key_norm
from .pdf_review import PdfInspection, PdfReviewCandidate, inspect_pdf_candidate, score_review_candidate
from .upcitemdb_provider import lookup_identity_by_trade_code, trade_codes_equivalent


@dataclass(frozen=True)
class ResolvedPdfIdentity:
    raw: ProductIdentity
    identity: ProductIdentity
    official_domain: str | None
    status: str
    confidence: float
    diagnostics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ValidatedPdfCandidate:
    candidate: PdfReviewCandidate
    inspection: PdfInspection
    sha256: str
    state: str = "VALIDATED"


@dataclass(frozen=True)
class ReviewDiscoveryResult:
    resolved: ResolvedPdfIdentity
    candidates: tuple[ValidatedPdfCandidate, ...]
    discovered_count: int
    downloaded_count: int
    validated_count: int
    rejected_count: int
    duplicate_count: int
    # Physical/validated PDF variants remain separately countable for audit.
    # Coverage metrics collapse language copies of the same exact document.
    unique_document_count: int = 0
    language_variant_count: int = 0
    canonical_documents: tuple[dict, ...] = field(default_factory=tuple)


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", key_norm(value or ""))


def _strong_keys(identity: ProductIdentity) -> set[str]:
    return {
        _compact(value)
        for value in (identity.mpn, identity.ean, identity.upc, identity.gtin, identity.sku)
        if value
    }


def _primary_strong_value(identity: ProductIdentity) -> str | None:
    for value in (identity.mpn, identity.ean, identity.upc, identity.gtin, identity.sku):
        text = str(value or "").strip()
        if text:
            return text
    return None


def _input_is_code_only(identity: ProductIdentity) -> bool:
    strong = _strong_keys(identity)
    model = _compact(identity.model)
    product_name = _compact(identity.product_name)
    return bool(strong and ((model and model in strong) or (product_name and product_name in strong)))


def _has_descriptive_model(identity: ProductIdentity) -> bool:
    strong = _strong_keys(identity)
    raw = _primary_strong_value(identity)
    for value in (identity.model, identity.product_name):
        text = str(value or "").strip()
        if text and _compact(text) not in strong and len(text) <= 100 and model_sanity_pass(text, raw=raw):
            return True
    return False


def _trade_lookup_identifier(identity: ProductIdentity) -> str | None:
    for value in (identity.ean, identity.upc, identity.gtin):
        text = re.sub(r"\D", "", str(value or ""))
        if 8 <= len(text) <= 14:
            return text
    return None


def _provider_trade_codes(identity: ProductIdentity | None) -> list[str]:
    if identity is None:
        return []
    return [str(value) for value in (identity.ean, identity.upc, identity.gtin) if value]


def _provider_conflicts_with_input(original: ProductIdentity, provider_identity: ProductIdentity | None) -> bool:
    provider_codes = _provider_trade_codes(provider_identity)
    if not provider_codes:
        return False
    for original_code in (original.ean, original.upc, original.gtin):
        if not original_code:
            continue
        if not any(trade_codes_equivalent(original_code, candidate) for candidate in provider_codes):
            return True
    return False


def _merge_provider_identity(original: ProductIdentity, current: ProductIdentity, provider: ProductIdentity) -> ProductIdentity:
    strong = _strong_keys(original)
    updates = {}
    raw = _primary_strong_value(original)
    if provider.brand and brand_sanity_pass(provider.brand, raw=raw) and (
        not current.brand or not brand_sanity_pass(current.brand, raw=raw) or len(str(current.brand).strip()) > 60
    ):
        updates["brand"] = provider.brand
    provider_model = provider.model or provider.product_name
    if provider_model and _compact(provider_model) not in strong and model_sanity_pass(provider_model, raw=raw) and (
        not _has_descriptive_model(current)
        or len(str(provider_model).strip()) < len(str(current.model or current.product_name or "").strip())
    ):
        updates["model"] = provider_model
        updates["product_name"] = provider.product_name or provider_model
    if provider.manufacturer and not current.manufacturer:
        updates["manufacturer"] = provider.manufacturer
    for field_name in ("ean", "upc", "gtin"):
        if getattr(provider, field_name, None) and not getattr(current, field_name, None):
            updates[field_name] = getattr(provider, field_name)
    return current.model_copy(update=updates) if updates else current


def _retail_domain_hint(url: str | None) -> str | None:
    host = (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")
    return host or None


def _guess_brand_from_model(model: str | None) -> str | None:
    text = str(model or "").strip()
    if not text:
        return None
    first = re.split(r"[\s/_-]+", text)[0].strip()
    if 2 <= len(first) <= 30 and first.isalpha():
        return first
    return None


def _identity_confidence(identity: ProductIdentity) -> float:
    confidence = float(identity.confidence or 0.0)
    if identity.brand:
        confidence = max(confidence, 0.65)
    if identity.model or identity.product_name:
        confidence = max(confidence, 0.72)
    if _strong_keys(identity):
        confidence = max(confidence, 0.82)
    return min(1.0, confidence)


def _resolved_status(identity: ProductIdentity, original: ProductIdentity) -> str:
    if identity.identifiers_conflicting:
        return "CONFLICT"
    if identity.brand and _has_descriptive_model(identity):
        return "RESOLVED"
    if identity.brand or _has_descriptive_model(identity):
        return "PARTIAL_IDENTITY"
    if _strong_keys(original):
        return "PARTIAL_IDENTITY"
    return "UNKNOWN"


def resolve_pdf_identity(
    identity: ProductIdentity,
    *,
    timeout: int = 10,
    lookup_trade_code: Callable[[str], ProductIdentity | None] | None = None,
) -> ResolvedPdfIdentity:
    """Resolve enough identity for PDF discovery while preserving exact input IDs."""
    original = identity.model_copy(deep=True)
    current = identity.model_copy(deep=True)
    diagnostics: dict = {"steps": []}
    provider = lookup_trade_code or lookup_identity_by_trade_code

    trade_code = _trade_lookup_identifier(original)
    if trade_code:
        diagnostics["steps"].append("TRADE_CODE_LOOKUP")
        try:
            provider_identity = provider(trade_code)
        except Exception as exc:
            provider_identity = None
            diagnostics["trade_code_error"] = f"{type(exc).__name__}: {exc}"
        if provider_identity is not None:
            if _provider_conflicts_with_input(original, provider_identity):
                current.identifiers_conflicting.append("GTIN_CONFLICT")
                diagnostics["trade_code_conflict"] = True
            else:
                current = _merge_provider_identity(original, current, provider_identity)
                diagnostics["trade_code_match"] = True

    if _input_is_code_only(current) or not current.brand or not _has_descriptive_model(current):
        diagnostics["steps"].append("REFINE_CODE_IDENTITY")
        try:
            refinement = refine_code_identity(current, timeout=timeout)
        except Exception as exc:
            refinement = None
            diagnostics["refinement_error"] = f"{type(exc).__name__}: {exc}"
        if refinement is not None:
            candidate = refinement.identity
            if candidate and identity_sanity_pass(candidate, raw=_primary_strong_value(original)):
                current = candidate
                diagnostics["refinement_status"] = refinement.status
                diagnostics["refinement_confidence"] = refinement.confidence
                diagnostics["refinement_source"] = refinement.source
                diagnostics["refinement_evidence"] = list(refinement.evidence)
            else:
                diagnostics["refinement_rejected"] = True

    if not current.brand:
        guessed = _guess_brand_from_model(current.model or current.product_name)
        if guessed and brand_sanity_pass(guessed, raw=_primary_strong_value(original)):
            current.brand = guessed
            diagnostics["brand_guess"] = guessed

    # Exact user identifiers are immutable. Refinement may enrich but cannot erase them.
    for field_name in ("mpn", "sku", "ean", "upc", "gtin"):
        original_value = getattr(original, field_name, None)
        if original_value:
            setattr(current, field_name, original_value)
    current.confidence = max(float(current.confidence or 0), _identity_confidence(current))
    status = _resolved_status(current, original)
    diagnostics["status"] = status
    return ResolvedPdfIdentity(
        raw=original,
        identity=current,
        official_domain=None,
        status=status,
        confidence=current.confidence,
        diagnostics=diagnostics,
    )


def _review_candidate(candidate) -> PdfReviewCandidate:
    return PdfReviewCandidate(
        url=candidate.url,
        title=getattr(candidate, "title", "") or "",
        document_type=getattr(candidate, "document_type", "") or "",
        likely_official=bool(getattr(candidate, "likely_official", False)),
        discovery_score=float(getattr(candidate, "score", 0.0) or 0.0),
        review_score=float(getattr(candidate, "score", 0.0) or 0.0),
        identity_status=str(getattr(candidate, "identity_status", "UNKNOWN") or "UNKNOWN"),
        identity_reason=str(getattr(candidate, "identity_reason", "") or ""),
        identity_score=float(getattr(candidate, "identity_score", 0.0) or 0.0),
        provenance=getattr(candidate, "provenance", None),
    )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
