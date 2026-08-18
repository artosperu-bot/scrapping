from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from rapidfuzz import fuzz

from .evidence_quality import generic_evidence_gate, strict_semantic_gate
from .final_evidence_gate import evaluate_field_write
from .models import Evidence, ProductRecord
from .normalize import ALIASES, canonical_key, key_norm
from .semantic_guard import FieldContract, validate_value


@dataclass
class Candidate:
    value: Any
    evidence: Evidence
    score: float
    canonical: str | None
    reasons: list[str]


def _alias_terms(key: str) -> list[str]:
    return [key.replace("_", " "), *(ALIASES.get(key) or [])]


def semantic_similarity(field_label: str, field_description: str | None, ev: Evidence, target_canonical: str | None) -> float:
    attr = key_norm(ev.attribute)
    label = key_norm(field_label)
    desc = key_norm(field_description or "")
    score = 0.0
    if target_canonical:
        ev_can = canonical_key(ev.attribute)
        if ev_can == target_canonical:
            score = 1.0
        else:
            aliases = [key_norm(x) for x in _alias_terms(target_canonical)]
            score = max([fuzz.ratio(attr, a) / 100 for a in aliases] + [0.0])
            if any(a and a in attr for a in aliases):
                score = max(score, .94)
    if not target_canonical:
        score = fuzz.ratio(attr, label) / 100
    # Description helps only a little; it must never override an unrelated attribute.
    if desc and len(attr) >= 4 and attr in desc:
        score = max(score, .90)
    return score


def iter_clean_evidence(rec: ProductRecord) -> Iterable[tuple[Evidence, float]]:
    for ev in rec.evidence:
        ok, _, q = generic_evidence_gate(ev)
        if ok:
            yield ev, q


def _number_and_unit(value: Any) -> tuple[float, str] | None:
    text = str(value or "").strip().lower().replace(",", ".")
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(kg|g|mg|lb|lbs|oz|mm|cm|m|in|inch|inches)\b", text, re.I)
    if not m:
        return None
    return float(m.group(1)), m.group(2).lower()


def _compact_number(value: float) -> int | float:
    rounded = round(value, 6)
    return int(rounded) if float(rounded).is_integer() else rounded


def normalize_value_for_excel(value: Any, field_description: str | None, contract: FieldContract) -> tuple[Any, str | None]:
    """Convert an evidence value to the unit explicitly required by the Excel contract.

    Marketplace descriptions often say that a *number* will be interpreted as kg or cm.
    In those fields writing ``0.72 lb`` is semantically wrong even though lb is a valid
    mass unit. We therefore preserve raw evidence separately and convert only the final
    output value when the template explicitly declares its expected unit.
    """
    desc = key_norm(field_description or "")
    parsed = _number_and_unit(value)
    if not parsed:
        return value, None
    number, unit = parsed

    target = None
    if any(x in desc for x in ["se tomara como kilos", "se tomará como kilos", "taken as kilos", "taken as kilograms", "number will be taken as kilos"]):
        target = "kg"
    elif any(x in desc for x in ["se tomara como centimetros", "se tomará como centímetros", "taken as centimeters", "number will be taken as centimeters"]):
        target = "cm"

    if target == "kg" and contract.allowed_dimensions and "mass" in contract.allowed_dimensions:
        factors = {"kg": 1.0, "g": 0.001, "mg": 0.000001, "lb": 0.45359237, "lbs": 0.45359237, "oz": 0.028349523125}
        if unit in factors:
            return _compact_number(number * factors[unit]), f"normalized_{unit}_to_kg_for_excel"

    if target == "cm" and contract.allowed_dimensions and "length" in contract.allowed_dimensions:
        factors = {"cm": 1.0, "mm": 0.1, "m": 100.0, "in": 2.54, "inch": 2.54, "inches": 2.54}
        if unit in factors:
            return _compact_number(number * factors[unit]), f"normalized_{unit}_to_cm_for_excel"

    return value, None


def candidates_for_field(
    rec: ProductRecord,
    field_label: str,
    field_description: str | None,
    target_canonical: str | None,
    contract: FieldContract,
) -> list[Candidate]:
    out: list[Candidate] = []
    gate_field = target_canonical or contract.semantic or field_label
    for ev, q in iter_clean_evidence(rec):
        # Identity/provenance is load-bearing and is checked before semantic
        # similarity/scoring. A sibling document can therefore never compensate
        # for a hard conflict by having a very high text similarity score.
        write_decision = evaluate_field_write(rec, gate_field, ev)
        if not write_decision.allowed:
            continue
        sim = semantic_similarity(field_label, field_description, ev, target_canonical)
        if sim < .88:
            continue
        ev_can = canonical_key(ev.attribute)
        can = target_canonical or ev_can
        sem_ok, sem_reason = strict_semantic_gate(can, ev)
        if not sem_ok:
            continue
        raw_value = ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value
        ok, guard_reason, guard_conf = validate_value(
            raw_value, contract, evidence_attribute=ev.attribute, evidence_raw=ev.raw_value
        )
        if not ok:
            continue
        value, normalization_reason = normalize_value_for_excel(raw_value, field_description, contract)
        # Exact semantic identity dominates raw model confidence.
        score = (sim * .52) + (q * .30) + (guard_conf * .18)
        reasons = [f"semantic={sim:.3f}", f"quality={q:.3f}", guard_reason, sem_reason, f"write_gate={write_decision.reason}"]
        if normalization_reason:
            reasons.append(normalization_reason)
        out.append(Candidate(value, ev, score, can, reasons))
    out.sort(key=lambda c: c.score, reverse=True)
    return out


def best_candidate(*args, **kwargs) -> Candidate | None:
    cs = candidates_for_field(*args, **kwargs)
    if not cs:
        return None
    # Do not write if the best evidence is only marginally semantically related.
    return cs[0] if cs[0].score >= .82 else None


def find_explicit_evidence(rec: ProductRecord, patterns: list[str]) -> list[Evidence]:
    out=[]
    for ev, _q in iter_clean_evidence(rec):
        hay=key_norm(f"{ev.attribute} {ev.raw_value} {ev.normalized_value}")
        if any(re.search(p, hay,re.I) for p in patterns):
            out.append(ev)
    return out
