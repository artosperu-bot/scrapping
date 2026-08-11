from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from rapidfuzz import fuzz

from .evidence_quality import generic_evidence_gate, strict_semantic_gate
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


def candidates_for_field(
    rec: ProductRecord,
    field_label: str,
    field_description: str | None,
    target_canonical: str | None,
    contract: FieldContract,
) -> list[Candidate]:
    out: list[Candidate] = []
    for ev, q in iter_clean_evidence(rec):
        sim = semantic_similarity(field_label, field_description, ev, target_canonical)
        if sim < .88:
            continue
        ev_can = canonical_key(ev.attribute)
        can = target_canonical or ev_can
        sem_ok, sem_reason = strict_semantic_gate(can, ev)
        if not sem_ok:
            continue
        value = ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value
        ok, guard_reason, guard_conf = validate_value(
            value, contract, evidence_attribute=ev.attribute, evidence_raw=ev.raw_value
        )
        if not ok:
            continue
        # Exact semantic identity dominates raw model confidence.
        score = (sim * .52) + (q * .30) + (guard_conf * .18)
        reasons = [f"semantic={sim:.3f}", f"quality={q:.3f}", guard_reason, sem_reason]
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
        if any(re.search(p, hay, re.I) for p in patterns):
            out.append(ev)
    return out
