from __future__ import annotations

from dataclasses import dataclass
import re

from .models import Evidence, ProductRecord


EXACT_DOCUMENT_RELATIONSHIPS = {"EXACT_SKU", "EXACT_MODEL"}
_VALID_IDENTITY_STATES = {"EXACT", "HIGH", "COMPATIBLE"}

# Fields whose value can vary while the functional model stays the same. A
# MODEL-scoped document is useful for shared technical specs but cannot, by
# itself, prove these SKU-sensitive values.
_SKU_SENSITIVE_EXACT = {
    "color",
    "colour",
    "mpn",
    "sku",
    "ean",
    "upc",
    "gtin",
    "barcode",
    "manufacturer part number",
    "manufacturer sku",
    "regional bundle",
    "region",
    "storage",
    "storage capacity",
    "memory configuration",
    "ram configuration",
    "included accessories",
    "package contents",
    "bundle",
}
_SKU_SENSITIVE_PATTERNS = (
    r"\b(color|colour)\b",
    r"\b(ean|upc|gtin|barcode|mpn|sku)\b",
    r"\bstorage\s+(capacity|configuration)\b",
    r"\b(memory|ram)\s+configuration\b",
    r"\b(regional?\s+bundle|included\s+accessories|package\s+contents)\b",
)


@dataclass(frozen=True)
class FieldWriteDecision:
    allowed: bool
    reason: str
    field: str
    document_scope: str | None = None
    document_relationship: str | None = None


def _norm_field(value: str | None) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[_-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_sku_sensitive_field(field: str | None) -> bool:
    normalized = _norm_field(field)
    if normalized in _SKU_SENSITIVE_EXACT:
        return True
    return any(re.search(pattern, normalized, re.I) for pattern in _SKU_SENSITIVE_PATTERNS)


def _record_has_hard_conflict(record: ProductRecord) -> bool:
    if record.identity.match_level == "CONFLICT" or record.identity.identifiers_conflicting:
        return True
    for conflict in record.conflicts:
        if not isinstance(conflict, dict):
            continue
        severity = str(conflict.get("severity") or conflict.get("level") or "").upper()
        status = str(conflict.get("status") or "").upper()
        if severity in {"HARD", "BLOCKING", "CRITICAL"} or status in {"UNRESOLVED", "CONFLICT"}:
            return True
    return False


def evaluate_field_write(record: ProductRecord, field: str, evidence: Evidence | None) -> FieldWriteDecision:
    """Final fail-closed barrier before a source fact can become an Excel value.

    Upstream extraction can discover candidates, but a field becomes write-eligible
    only when product identity, source policy and document relationship all remain
    valid at the final boundary.
    """
    normalized_field = _norm_field(field)

    identity_state = str(record.identity.match_level or "LOW").upper()
    if identity_state not in {"EXACT", "HIGH"} or _record_has_hard_conflict(record):
        return FieldWriteDecision(False, "PRODUCT_IDENTITY_NOT_VALID", normalized_field)

    if evidence is None:
        return FieldWriteDecision(False, "FIELD_EVIDENCE_MISSING", normalized_field)

    if evidence.policy_allowed is False:
        return FieldWriteDecision(False, "EVIDENCE_POLICY_REJECTED", normalized_field)

    if evidence.identity_status and str(evidence.identity_status).upper() not in _VALID_IDENTITY_STATES:
        return FieldWriteDecision(False, "EVIDENCE_IDENTITY_NOT_VALID", normalized_field)

    if evidence.hard_conflicts:
        return FieldWriteDecision(
            False,
            "UNRESOLVED_HARD_CONFLICT",
            normalized_field,
            evidence.document_scope,
            evidence.document_relationship,
        )

    source_is_pdf = "pdf" in str(evidence.source_type or "").casefold()
    relationship = str(evidence.document_relationship or "").upper() or None
    scope = str(evidence.document_scope or "").upper() or None

    # Once a PDF carries relationship metadata, it is authoritative for admission.
    # Non-exact classes can never be recovered by source authority or provenance.
    if relationship and relationship not in EXACT_DOCUMENT_RELATIONSHIPS:
        return FieldWriteDecision(False, "DOCUMENT_RELATIONSHIP_NOT_EXACT", normalized_field, scope, relationship)

    # New PDF evidence must be explicitly bound to the product before it is used.
    # Legacy PDF producers without metadata are kept compatible only until they
    # are routed through the hardened pipeline; they are not granted SKU scope.
    if source_is_pdf and relationship is None and evidence.policy_allowed is True:
        return FieldWriteDecision(False, "PDF_RELATIONSHIP_UNPROVEN", normalized_field, scope, relationship)

    if (relationship == "EXACT_MODEL" or scope == "MODEL") and is_sku_sensitive_field(normalized_field):
        return FieldWriteDecision(False, "MODEL_SCOPE_CANNOT_PROVE_SKU_FIELD", normalized_field, scope, relationship)

    return FieldWriteDecision(True, "EVIDENCE_PROVEN_FOR_FIELD", normalized_field, scope, relationship)
