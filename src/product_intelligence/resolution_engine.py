from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz

from .canonical_facts import build_canonical_facts, canonical_invariant_errors
from .models import ProductRecord
from .normalize import canonical_key, key_norm

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
    FOUND_DIRECT, FOUND_DERIVED, FOUND_MAPPED, FOUND_CLASSIFIED, SELLER_REQUIRED,
    NOT_APPLICABLE, NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS, INSUFFICIENT_EVIDENCE,
    CONFLICTING_EVIDENCE,
}


def _phrase(value: Any) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    return key_norm(value.replace("_", " ").replace("-", " "))


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


def _not_applicable(facts: dict[str, Any], semantic: str) -> tuple[bool, str]:
    s = _phrase(semantic)
    if any(x in s for x in ["autonomia", "battery life", "play time", "runtime"]):
        if facts["connectivity"].get("wired") is True and facts["battery"].get("present") is False:
            return True, "wired_product_without_internal_battery"
    return False, ""


def _canonical_resolves(facts: dict[str, Any], semantic: str) -> tuple[bool, str, str]:
    s = _phrase(semantic)
    conn = facts.get("connectivity", {})
    bt = conn.get("bluetooth", {})
    battery = facts.get("battery", {})
    durability = facts.get("durability", {})

    if "bluetooth" in s and bt.get("present") is not None:
        return True, FOUND_DERIVED, "canonical_bluetooth_presence"
    if any(x in s for x in ["conectividad", "connectivity", "conexion"]):
        if any([conn.get("usb_c"), conn.get("usb"), conn.get("jack_3_5mm"), conn.get("rf_2_4ghz"), conn.get("wifi"), conn.get("nfc"), bt.get("present") is True, conn.get("wired") is True, conn.get("wireless") is True]):
            return True, FOUND_MAPPED, "canonical_connectivity_transports"
    if any(x in s for x in ["resistente al agua", "water resistance", "ip rating", "proteccion agua"]):
        if durability.get("water_rating") is not None or durability.get("ip_rating") is not None:
            return True, FOUND_DERIVED, "canonical_ip_water_component"
    if any(x in s for x in ["autonomia", "battery life", "play time", "runtime"]):
        if battery.get("runtime_hours") is not None:
            return True, FOUND_DERIVED, "canonical_battery_runtime"
    if any(x in s for x in ["alimentacion", "power source", "fuente de energia"]):
        if battery.get("rechargeable") is True or (battery.get("present") is False and conn.get("wired") is True and (conn.get("usb_c") or conn.get("usb"))):
            return True, FOUND_DERIVED, "canonical_power_relation"
    if any(x in s for x in ["tipo de auricular", "headphone type", "form factor"]):
        if facts.get("form_factor"):
            return True, FOUND_MAPPED, "canonical_form_factor"
    if any(x in s for x in ["segmento", "segment", "activity", "actividad"]):
        if facts.get("semantic_segment"):
            return True, FOUND_CLASSIFIED, "canonical_semantic_segment"
    if any(x in s for x in ["codigo de barras", "barcode", "ean", "upc", "gtin"]):
        if facts.get("identity", {}).get("gtin"):
            return True, FOUND_DIRECT, "canonical_gtin"
    if "driver" in s and facts.get("driver_size_mm") is not None:
        return True, FOUND_DIRECT, "canonical_driver_size"
    return False, "", ""


def cross_field_issues(rec: ProductRecord, facts: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    facts = facts or build_canonical_facts(rec)
    issues = []

    bt_false = False
    bt_version = False
    for ev in rec.evidence:
        if canonical_key(ev.attribute) != "bluetooth":
            continue
        raw = str(ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value or "").strip()
        n = key_norm(raw)
        if n in {"no", "false", "0", "not supported", "unsupported"}:
            bt_false = True
        if re.search(r"\b(?:bluetooth\s*)?\d(?:\.\d)?\b", raw, re.I):
            bt_version = True
    if bt_false and bt_version:
        issues.append({
            "code": "BLUETOOTH_CONTRADICTION",
            "severity": "BLOCK",
            "research_semantic": "bluetooth",
            "message": "Evidencia limpia mantiene Bluetooth=No y una versión Bluetooth; requiere resolver variante/fuente.",
        })

    battery = facts["battery"]
    if battery.get("present") is False and battery.get("runtime_hours") is not None:
        issues.append({
            "code": "BATTERY_RUNTIME_CONTRADICTION",
            "severity": "BLOCK",
            "research_semantic": "battery life",
            "message": "Producto sin batería conserva una autonomía numérica después de normalización.",
        })

    for code in canonical_invariant_errors(facts):
        if not any(x.get("code") == code for x in issues):
            issues.append({
                "code": code,
                "severity": "BLOCK",
                "research_semantic": None,
                "message": "Invariante semántico canónico incumplido; no se permite escribir silenciosamente.",
            })
    return issues


def analyze_resolution(rec: ProductRecord, template_plan: dict | None) -> dict[str, Any]:
    semantics = list(dict.fromkeys(str(x) for x in ((template_plan or {}).get("scrape_semantics") or []) if x))
    facts = build_canonical_facts(rec)
    conflict_keys = {_phrase(c.get("attribute")) for c in (rec.conflicts or []) if c.get("attribute")}
    fields = []
    research = []

    for semantic in semantics:
        normalized = _phrase(semantic)
        is_conflict = any(fuzz.ratio(normalized, c) / 100 >= .88 for c in conflict_keys if c)
        if is_conflict:
            status = CONFLICTING_EVIDENCE
            reason = "normalized_unique_values_still_conflict"
            research.append(semantic)
        else:
            na, na_reason = _not_applicable(facts, semantic)
            direct = _semantic_has_direct_evidence(rec, semantic)
            canonical_ok, canonical_status, canonical_reason = _canonical_resolves(facts, semantic)
            if na:
                status = NOT_APPLICABLE
                reason = na_reason
            elif direct:
                status = FOUND_DIRECT
                reason = "validated_evidence_matches_field_semantics"
            elif canonical_ok:
                status = canonical_status
                reason = canonical_reason
            else:
                status = INSUFFICIENT_EVIDENCE
                reason = "no_validated_evidence_or_canonical_fact_for_requested_semantic"
                research.append(semantic)
        fields.append({"semantic": semantic, "status": status, "reason": reason})

    issues = cross_field_issues(rec, facts)
    for issue in issues:
        term = issue.get("research_semantic")
        if term and term not in research:
            research.insert(0, term)

    return {
        "fields": fields,
        "counts": {state: sum(1 for row in fields if row["status"] == state) for state in FINAL_STATES},
        "research_terms": research[:8],
        "cross_field_issues": issues,
        "canonical_invariant_errors": canonical_invariant_errors(facts),
        "blocked": any(issue.get("severity") == "BLOCK" for issue in issues),
        "canonical_facts": facts,
    }
