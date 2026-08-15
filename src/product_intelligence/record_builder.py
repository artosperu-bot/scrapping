from __future__ import annotations

from collections import defaultdict

from .evidence_quality import generic_evidence_gate, strict_semantic_gate
from .evidence_policy import ConsensusFact, resolve_evidence_group
from .models import Evidence, ProductIdentity, ProductRecord
from .normalize import canonical_key, key_norm
from .source_authority import effective_quality, source_family


def _evidence_key(ev: Evidence) -> tuple[str, str, str, str]:
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
    brand_spec = (specs.get("brand") or {}).get("value")
    if brand_spec:
        if not identity.brand or not _identity_token_supported(identity.brand, identity):
            identity.brand = str(brand_spec)
    model_spec = (specs.get("model") or {}).get("value")
    if model_spec and not identity.model:
        identity.model = str(model_spec)
    return identity


def _consensus_authority(ev: Evidence) -> str:
    family = source_family(ev)
    return {
        "manufacturer": "manufacturer",
        "official_pdf": "official_pdf",
        "technical_document": "technical_document",
        "regulatory": "technical_database",
        "structured_catalog": "technical_database",
        "distributor": "authorized_distributor",
        "secondary": "retailer",
        "marketplace": "marketplace",
        "unknown": "third_party",
    }.get(family, "third_party")


def _consensus_identity(ev: Evidence) -> str:
    level = str(ev.match_level or "").upper()
    if level == "EXACT":
        return "EXACT"
    if level in {"HIGH", "MEDIUM"}:
        return "COMPATIBLE"
    return "AMBIGUOUS"


def _normalized_fact_value(ev: Evidence) -> str:
    return key_norm(str(ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value))


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
    consensus_audit: dict[str, dict] = {}

    for key, rows in grouped.items():
        rows.sort(key=lambda item: (item[2], item[1], float(item[0].confidence or 0)), reverse=True)
        consensus = resolve_evidence_group([
            ConsensusFact(
                value=ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value,
                source_url=str(ev.source_url or ""),
                authority=_consensus_authority(ev),
                identity_status=_consensus_identity(ev),
                confidence=float(ev.confidence or 0.0),
            )
            for ev, _q_value, _authority in rows
        ])
        consensus_audit[key] = {
            "status": consensus.status,
            "reason": consensus.reason,
            "supporting_urls": list(consensus.supporting_urls),
            "rejected_urls": list(consensus.rejected_urls),
        }

        if consensus.accepted_value is None:
            rejected.append({
                "attribute": key,
                "value": None,
                "reason": consensus.reason,
                "source": None,
            })
            if consensus.reason == "SOURCE_CONFLICT":
                values = []
                for ev, q_value, auth in rows:
                    values.append({
                        "value": ev.normalized_value,
                        "source": ev.source_url,
                        "source_family": source_family(ev),
                        "confidence": round(q_value, 4),
                        "authority_rank": auth,
                    })
                conflicts.append({"attribute": key, "values": values[:12], "reason": "SOURCE_CONFLICT"})
            continue

        accepted_norm = key_norm(str(consensus.accepted_value))
        matching_rows = [row for row in rows if _normalized_fact_value(row[0]) == accepted_norm]
        if not matching_rows:
            matching_rows = rows
        top, quality, authority = max(matching_rows, key=lambda item: (item[2], item[1], float(item[0].confidence or 0)))
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
            "consensus_reason": consensus.reason,
            "supporting_sources": list(consensus.supporting_urls),
        }

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
        "consensus": consensus_audit,
    }
    return record
