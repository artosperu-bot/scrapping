from __future__ import annotations

from collections import defaultdict

from .evidence_quality import generic_evidence_gate, strict_semantic_gate
from .models import Evidence, ProductIdentity, ProductRecord
from .normalize import canonical_key, key_norm
from .source_authority import effective_quality, source_family


def _evidence_key(ev: Evidence) -> tuple[str, str, str, str]:
    """A duplicated DOM/JSON rendering is one piece of evidence, not multiple votes."""
    canonical = canonical_key(ev.attribute) or key_norm(ev.attribute)
    value = key_norm(str(ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value))
    source = str(ev.source_url or "").strip().lower()
    scope = str(ev.match_level or "")
    return canonical, value, source, scope


def _identity_token_supported(value: str | None, identity: ProductIdentity) -> bool:
    if not value:
        return False
    needle = key_norm(value).replace(" ", "")
    text = key_norm(" ".join(x for x in [identity.product_name, identity.model] if x)).replace(" ", "")
    return bool(needle and needle in text)


def _reconcile_identity(identity: ProductIdentity, specs: dict) -> ProductIdentity:
    """Keep seller/organization metadata separate from product identity."""
    brand_spec = (specs.get("brand") or {}).get("value")
    if brand_spec:
        if not identity.brand or not _identity_token_supported(identity.brand, identity):
            identity.brand = str(brand_spec)
    model_spec = (specs.get("model") or {}).get("value")
    if model_spec and not identity.model:
        identity.model = str(model_spec)
    return identity


def build_record_strict(identity: ProductIdentity, evidence: list[Evidence], sources: list[str]) -> ProductRecord:
    grouped: dict[str, list[tuple[Evidence, float, int]]] = defaultdict(list)
    additional: dict[str, list[Evidence]] = {}
    clean: list[Evidence] = []
    rejected: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    duplicates = 0

    for ev in evidence:
        ok, reason, quality = generic_evidence_gate(ev)
        if not ok:
            rejected.append({"attribute": ev.attribute, "value": ev.raw_value, "reason": reason, "source": ev.source_url})
            continue
        evidence_key = _evidence_key(ev)
        if evidence_key in seen:
            duplicates += 1
            continue
        seen.add(evidence_key)
        clean.append(ev)
        canonical = canonical_key(ev.attribute)
        if canonical:
            semantic_ok, semantic_reason = strict_semantic_gate(canonical, ev)
            if not semantic_ok:
                additional.setdefault(ev.attribute, []).append(ev)
                rejected.append({"attribute": ev.attribute, "value": ev.raw_value, "reason": semantic_reason, "source": ev.source_url})
                continue
            authority, capped_quality = effective_quality(canonical, ev, quality)
            grouped[canonical].append((ev, capped_quality, authority))
        else:
            additional.setdefault(ev.attribute, []).append(ev)

    specs = {}
    conflicts = []
    for key, rows in grouped.items():
        rows.sort(key=lambda item: (item[2], item[1], float(item[0].confidence or 0)), reverse=True)
        top, quality, authority = rows[0]
        specs[key] = {
            "value": top.normalized_value,
            "raw_value": top.raw_value,
            "unit": top.unit,
            "source": top.source_url,
            "source_type": top.source_type,
            "source_family": source_family(top),
            "selector": top.selector,
            "confidence": round(min(1.0, quality), 4),
            "original_confidence": top.confidence,
            "authority_rank": authority,
        }

        # Duplicates from one source are one vote. A lower-authority source does not create a
        # material conflict against a higher-authority fact unless it is close enough to matter.
        values: dict[str, list[tuple[Evidence, float, int]]] = defaultdict(list)
        for ev, q_value, auth in rows:
            normalized = key_norm(str(ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value))
            if normalized:
                values[normalized].append((ev, q_value, auth))
        if len(values) > 1:
            distinct = []
            for same_value_rows in values.values():
                best = max(same_value_rows, key=lambda item: (item[2], item[1]))
                ev, q_value, auth = best
                distinct.append((ev, q_value, auth))
            distinct.sort(key=lambda item: (item[2], item[1]), reverse=True)
            winning_authority = distinct[0][2]
            material = [item for item in distinct if item[2] >= max(1, winning_authority - 1) and item[1] >= .55]
            if len(material) > 1:
                conflicts.append({
                    "attribute": key,
                    "values": [
                        {
                            "value": ev.normalized_value,
                            "source": ev.source_url,
                            "source_family": source_family(ev),
                            "confidence": round(q_value, 4),
                            "authority_rank": auth,
                        }
                        for ev, q_value, auth in material[:12]
                    ],
                })

    identity = _reconcile_identity(identity, specs)
    record = ProductRecord(
        identity=identity,
        specifications=specs,
        additional_attributes=additional,
        evidence=clean,
        sources=list(dict.fromkeys(sources)),
        conflicts=conflicts,
    )
    record.warnings.append(f"evidence_rejected:{len(rejected)}")
    if duplicates:
        record.warnings.append(f"evidence_deduplicated:{duplicates}")
    record.evidence_graph = {
        "rejected_evidence": rejected[:300],
        "deduplicated_evidence_count": duplicates,
    }
    return record
