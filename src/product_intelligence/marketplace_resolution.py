from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

from .attribute_resolver import best_candidate
from .description_narrator import DescriptionNarrator
from .identifiers import validate_gtin
from .models import ProductRecord
from .normalize import key_norm
from .provider_runtime import current_settings, emit as emit_provider_event, mistral_narrator_client
from .semantic_guard import FieldContract, validate_value
from .smart_derivations import (
    derive_autonomy,
    derive_boolean,
    derive_connectivity,
    derive_description,
    derive_features,
    derive_headphone_type,
    derive_power_source,
    derive_segment,
    derive_water_resistance,
)

FOUND_DIRECT = "FOUND_DIRECT"
FOUND_MAPPED = "FOUND_MAPPED"
FOUND_DERIVED = "FOUND_DERIVED"
FOUND_CLASSIFIED = "FOUND_CLASSIFIED"
NOT_APPLICABLE = "NOT_APPLICABLE"
NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS = "NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS"
SELLER_REQUIRED = "SELLER_REQUIRED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"

FOUND_STATES = {FOUND_DIRECT, FOUND_MAPPED, FOUND_DERIVED, FOUND_CLASSIFIED}
IDENTITY_ALIASES = {"brand", "model", "mpn", "ean", "upc", "gtin", "product name"}
BARCODE_KEYS = {"ean", "upc", "gtin", "barcode", "codigo de barras", "código de barras"}


@dataclass
class FieldResult:
    field: str
    value: Any = None
    status: str = INSUFFICIENT_EVIDENCE
    confidence: float = 0.0
    source: str | None = None
    evidence_attribute: str | None = None
    evidence_raw: Any = None
    reason: str = ""
    transformation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_controlled(value: Any, options: list[Any]) -> tuple[Any | None, str]:
    if not options:
        return None, "NO_ALLOWED_OPTIONS"
    values = value if isinstance(value, list) else [x.strip() for x in re.split(r"[,;|]", str(value)) if x.strip()]
    out: list[Any] = []
    for item in values:
        normalized = key_norm(str(item))
        exact = next((o for o in options if key_norm(str(o)) == normalized), None)
        if exact is None:
            exact = next(
                (o for o in options if key_norm(str(o)).rstrip("s") == normalized.rstrip("s") and len(normalized) >= 4),
                None,
            )
        if exact is None:
            return None, f"VALUE_NOT_IN_ALLOWED_OPTIONS:{item}"
        if exact not in out:
            out.append(exact)
    return ", ".join(map(str, out)), "OK"


def _identity_value(rec: ProductRecord, key: str) -> tuple[Any, float]:
    attr = {"product name": "product_name"}.get(key, key)
    value = getattr(rec.identity, attr, None)
    if rec.identity.match_level == "EXACT":
        confidence = .99
    elif rec.identity.match_level == "HIGH":
        confidence = .90
    else:
        confidence = float(rec.identity.confidence or 0)
    return value, confidence


def _description_with_optional_narrator(rec: ProductRecord):
    """Keep deterministic derive_description() as the permanent fallback."""
    deterministic = derive_description(rec)
    if deterministic.value in (None, ""):
        return deterministic

    settings = current_settings()
    if not bool(settings.get("mistral_enabled", False)):
        return deterministic

    narrator = DescriptionNarrator(
        client=mistral_narrator_client(),
        enabled=True,
        model=str(settings.get("mistral_model") or "mistral-small-latest"),
        timeout=int(settings.get("request_timeout") or 20),
        audit=lambda event, data: emit_provider_event(event, **data),
    )
    narrated = narrator.describe(rec, fallback=lambda _rec: deterministic)
    if narrated is deterministic or not isinstance(narrated, str) or not narrated.strip():
        return deterministic

    derived_type = type(deterministic)
    return derived_type(
        value=narrated.strip(),
        confidence=max(.85, float(deterministic.confidence or 0)),
        reason="FOUND_DERIVED:mistral_grounded_description",
        source=deterministic.source,
        evidence_attribute=deterministic.evidence_attribute,
        evidence_raw=deterministic.evidence_raw,
    )


def _derived(rec: ProductRecord, header: str, description: str | None, canonical: str | None, contract: FieldContract, options: list[Any], external_id: str | None):
    h = key_norm(header)
    intent = key_norm(f"{header} {description or ''} {contract.semantic or ''}")
    derived = None
    if external_id == "53" or canonical == "description" or h in {"descripcion", "description"}:
        derived = _description_with_optional_narrator(rec)
    elif "bluetooth" in intent:
        derived = derive_boolean(rec, "bluetooth")
    elif "resistente al agua" in intent or "water resistance" in intent:
        derived = derive_water_resistance(rec, options)
    elif canonical == "connectivity" or "conectividad" in intent or "connectivity" in intent:
        derived = derive_connectivity(rec, options)
    elif canonical == "headphone type" or "tipo de auricular" in intent or "headphone type" in intent:
        derived = derive_headphone_type(rec, options)
    elif canonical == "power source" or "alimentacion" in intent or "power source" in intent:
        derived = derive_power_source(rec, options)
    elif canonical == "battery life" or "autonomia" in intent or "battery life" in intent:
        derived = derive_autonomy(rec)
    elif canonical == "features" or "caracteristicas" in intent or "features" in intent:
        derived = derive_features(rec, options)
    elif canonical == "segment" or "segmento" in intent:
        derived = derive_segment(rec, options)
    return derived


def _status_from_reason(reason: str, default: str) -> str:
    prefix = str(reason or "").split(":", 1)[0]
    if prefix in {
        FOUND_DIRECT, FOUND_MAPPED, FOUND_DERIVED, FOUND_CLASSIFIED,
        NOT_APPLICABLE, NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS,
        SELLER_REQUIRED, INSUFFICIENT_EVIDENCE, CONFLICTING_EVIDENCE,
    }:
        return prefix
    return default


def _is_barcode_field(field: str, evidence_attribute: str | None) -> bool:
    candidates = {key_norm(field), key_norm(evidence_attribute or "")}
    return any(item in BARCODE_KEYS or "codigo de barras" in item or "barcode" in item for item in candidates)


def _barcode_guard(value: Any, field: str, evidence_attribute: str | None) -> tuple[bool, str]:
    if not _is_barcode_field(field, evidence_attribute):
        return True, "NOT_BARCODE_FIELD"
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits or digits != str(value).strip():
        return False, "BARCODE_MUST_BE_NUMERIC"
    if len(digits) in {8, 12, 13, 14}:
        validation = validate_gtin(digits)
        if not validation.valid:
            return False, f"INVALID_{validation.gtin_type or 'GTIN'}:{validation.reason}"
    return True, "OK"


def _finalize(value: Any, confidence: float, contract: FieldContract, options: list[Any], *, field: str, source: str | None, evidence_attribute: str | None, evidence_raw: Any, reason: str, default_status: str, transformation: str | None = None) -> FieldResult:
    if value in (None, ""):
        return FieldResult(field=field, status=_status_from_reason(reason, INSUFFICIENT_EVIDENCE), confidence=confidence, source=source, evidence_attribute=evidence_attribute, evidence_raw=evidence_raw, reason=reason)

    status = _status_from_reason(reason, default_status)
    final_value = value
    mapped = False
    if contract.value_type == "controlled":
        final_value, mapping_reason = _coerce_controlled(value, options)
        if final_value is None:
            if str(mapping_reason).startswith("VALUE_NOT_IN_ALLOWED_OPTIONS"):
                return FieldResult(field=field, value=None, status=NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS, confidence=confidence, source=source, evidence_attribute=evidence_attribute, evidence_raw=evidence_raw, reason=mapping_reason, transformation="controlled_option_mapping")
            return FieldResult(field=field, value=None, status=INSUFFICIENT_EVIDENCE, confidence=confidence, source=source, evidence_attribute=evidence_attribute, evidence_raw=evidence_raw, reason=mapping_reason)
        mapped = key_norm(str(final_value)) != key_norm(str(value))

    barcode_ok, barcode_reason = _barcode_guard(final_value, field, evidence_attribute)
    if not barcode_ok:
        return FieldResult(field=field, value=None, status=INSUFFICIENT_EVIDENCE, confidence=0.0, source=source, evidence_attribute=evidence_attribute, evidence_raw=evidence_raw, reason=barcode_reason)

    ok, guard_reason, guard_conf = validate_value(final_value, contract, evidence_attribute=evidence_attribute, evidence_raw=evidence_raw)
    if not ok:
        return FieldResult(field=field, value=None, status=INSUFFICIENT_EVIDENCE, confidence=0.0, source=source, evidence_attribute=evidence_attribute, evidence_raw=evidence_raw, reason=guard_reason)

    if mapped and status == FOUND_DIRECT:
        status = FOUND_MAPPED
        transformation = transformation or "controlled_option_mapping"
    return FieldResult(
        field=field,
        value=final_value,
        status=status,
        confidence=round(min(float(confidence or 0), float(guard_conf or 1)), 4),
        source=source,
        evidence_attribute=evidence_attribute,
        evidence_raw=evidence_raw,
        reason=reason or guard_reason,
        transformation=transformation,
    )


def resolve_marketplace_field(
    rec: ProductRecord,
    *,
    header: str,
    description: str | None,
    canonical: str | None,
    contract: FieldContract,
    options: list[Any] | None = None,
    external_id: str | None = None,
) -> FieldResult:
    """Resolve a marketplace field completely before Excel sees it.

    The Excel writer must not infer product facts. This function owns identity selection,
    evidence selection, derivation/classification, option mapping and semantic validation.
    """
    options = list(options or [])
    field = canonical or contract.semantic or header

    derived = _derived(rec, header, description, canonical, contract, options, external_id)
    if derived is not None:
        derived_status = _status_from_reason(derived.reason, FOUND_DERIVED)
        if derived.value not in (None, "") and float(derived.confidence or 0) >= .85:
            return _finalize(
                derived.value,
                float(derived.confidence or 0),
                contract,
                options,
                field=field,
                source=derived.source,
                evidence_attribute=derived.evidence_attribute,
                evidence_raw=derived.evidence_raw,
                reason=derived.reason,
                default_status=derived_status,
                transformation="safe_derivation_or_classification",
            )
        if derived_status in {NOT_APPLICABLE, NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS, CONFLICTING_EVIDENCE}:
            return FieldResult(field=field, status=derived_status, confidence=float(derived.confidence or 0), reason=derived.reason, source=derived.source, evidence_attribute=derived.evidence_attribute, evidence_raw=derived.evidence_raw)

    if canonical in IDENTITY_ALIASES:
        value, confidence = _identity_value(rec, canonical)
        if value not in (None, "") and confidence >= .88:
            return _finalize(
                value,
                confidence,
                contract,
                options,
                field=field,
                source="identity",
                evidence_attribute=canonical,
                evidence_raw=value,
                reason="validated_product_identity",
                default_status=FOUND_DIRECT,
            )

    if canonical:
        candidate = best_candidate(rec, header, description, canonical, contract)
        if candidate:
            return _finalize(
                candidate.value,
                float(candidate.score or 0),
                contract,
                options,
                field=field,
                source=candidate.evidence.source_url,
                evidence_attribute=candidate.evidence.attribute,
                evidence_raw=candidate.evidence.raw_value,
                reason=";".join(candidate.reasons or []) or "validated_evidence_candidate",
                default_status=FOUND_DIRECT,
            )

    return FieldResult(field=field, status=INSUFFICIENT_EVIDENCE, reason="no_resolved_value_after_semantic_pipeline")
