from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz

from .models import ProductRecord
from .normalize import key_norm

FOUND_DIRECT = "FOUND_DIRECT"
FOUND_DERIVED = "FOUND_DERIVED"
FOUND_MAPPED = "FOUND_MAPPED"
FOUND_CLASSIFIED = "FOUND_CLASSIFIED"
SELLER_REQUIRED = "SELLER_REQUIRED"
NOT_APPLICABLE = "NOT_APPLICABLE"
NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS = "NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"

FINAL_STATES = {
    FOUND_DIRECT,
    FOUND_DERIVED,
    FOUND_MAPPED,
    FOUND_CLASSIFIED,
    SELLER_REQUIRED,
    NOT_APPLICABLE,
    NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS,
    INSUFFICIENT_EVIDENCE,
    CONFLICTING_EVIDENCE,
}


def _phrase(value: Any) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    return key_norm(value.replace("_", " ").replace("-", " "))


def _evidence_text(rec: ProductRecord) -> str:
    parts = [f"{ev.attribute} {ev.raw_value} {ev.normalized_value}" for ev in rec.evidence]
    parts += [str(v) for v in [rec.identity.product_name, rec.identity.model, rec.identity.brand] if v]
    return key_norm("\n".join(parts))


def _semantic_has_direct_evidence(rec: ProductRecord, semantic: str) -> bool:
    target = _phrase(semantic)
    if len(target) < 3:
        return False
    for ev in rec.evidence:
        attr = _phrase(ev.attribute)
        if not attr:
            continue
        score = fuzz.ratio(attr, target) / 100
        contained = (target in attr or attr in target) and min(len(attr), len(target)) >= 4
        if (score >= .88 or contained) and float(ev.confidence or 0) >= .70:
            return True
    return False


def _not_applicable(rec: ProductRecord, semantic: str) -> tuple[bool, str]:
    semantic_norm = _phrase(semantic)
    text = _evidence_text(rec)
    if any(x in semantic_norm for x in ["autonomia", "battery life", "play time", "runtime"]):
        wired = bool(re.search(r"\bwired\b|cableado|al[aá]mbric|usb[ -]?c wired", text, re.I))
        no_battery = bool(re.search(r"no battery|without battery|sin bater[ií]a|battery required\s*[:=]?\s*(no|false)", text, re.I))
        if wired and no_battery:
            return True, "wired_product_without_battery"
    return False, ""


def cross_field_issues(rec: ProductRecord) -> list[dict[str, Any]]:
    text = _evidence_text(rec)
    issues: list[dict[str, Any]] = []

    explicit_bt_no = bool(re.search(r"bluetooth[^\n:]{0,40}(?:[:=]|\bis\b)?\s*(no|false|not supported)", text, re.I))
    explicit_bt_yes = bool(re.search(r"bluetooth\s*(?:version|v)?\s*\d|bluetooth[^\n:]{0,30}(yes|true|supported)", text, re.I))
    if explicit_bt_no and explicit_bt_yes:
        issues.append({
            "code": "BLUETOOTH_CONTRADICTION",
            "severity": "BLOCK",
            "message": "La evidencia afirma Bluetooth=No y también demuestra presencia/versión Bluetooth.",
        })

    wired = bool(re.search(r"\bwired\b|cableado|al[aá]mbric", text, re.I))
    no_battery = bool(re.search(r"no battery|without battery|sin bater[ií]a", text, re.I))
    autonomy = bool(re.search(r"(?:battery life|play time|autonom[ií]a|runtime)[^\n]{0,80}\b\d+(?:[.,]\d+)?\s*(?:h|hr|hours?|horas?)\b", text, re.I))
    if wired and no_battery and autonomy:
        issues.append({
            "code": "WIRED_AUTONOMY_CONTRADICTION",
            "severity": "BLOCK",
            "message": "Producto cableado/sin batería presenta autonomía numérica incompatible.",
        })

    return issues


def analyze_resolution(rec: ProductRecord, template_plan: dict | None) -> dict[str, Any]:
    """Classify every requested product semantic into an auditable final state.

    This layer never invents values. It decides whether the current validated evidence is
    sufficient, conflicting, not applicable, or worth another targeted research pass.
    """
    semantics = list(dict.fromkeys(str(x) for x in ((template_plan or {}).get("scrape_semantics") or []) if x))
    conflict_keys = {_phrase(c.get("attribute")) for c in (rec.conflicts or []) if c.get("attribute")}
    fields: list[dict[str, Any]] = []
    research: list[str] = []

    for semantic in semantics:
        normalized = _phrase(semantic)
        if any(fuzz.ratio(normalized, conflict) / 100 >= .88 for conflict in conflict_keys if conflict):
            status = CONFLICTING_EVIDENCE
            reason = "multiple_high_quality_values"
        else:
            not_applicable, na_reason = _not_applicable(rec, semantic)
            if not_applicable:
                status = NOT_APPLICABLE
                reason = na_reason
            elif _semantic_has_direct_evidence(rec, semantic):
                status = FOUND_DIRECT
                reason = "validated_evidence_matches_field_semantics"
            else:
                status = INSUFFICIENT_EVIDENCE
                reason = "no_validated_evidence_for_requested_semantic"
                research.append(semantic)
        fields.append({"semantic": semantic, "status": status, "reason": reason})

    issues = cross_field_issues(rec)
    return {
        "fields": fields,
        "counts": {state: sum(1 for row in fields if row["status"] == state) for state in FINAL_STATES},
        "research_terms": research[:6],
        "cross_field_issues": issues,
        "blocked": any(issue.get("severity") == "BLOCK" for issue in issues),
    }
