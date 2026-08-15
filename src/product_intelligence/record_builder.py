from __future__ import annotations

from collections import defaultdict
import re

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


def _compact_identity(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", key_norm(str(value or "")))


def _identity_bound_evidence_ok(canonical: str, ev: Evidence, identity: ProductIdentity) -> tuple[bool, str]:
    expected = {
        "mpn": identity.mpn,
        "ean": identity.ean,
        "upc": identity.upc,
        "gtin": identity.gtin,
        "model": identity.model or identity.product_name,
        "brand": identity.brand,
    }.get(canonical)
    if not expected:
        return True, "NO_REQUESTED_IDENTITY_VALUE"

    value = ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value
    exp = _compact_identity(expected)
    got = _compact_identity(value)
    if not exp or not got:
        return False, "IDENTITY_VALUE_EMPTY"

    if canonical in {"mpn", "ean", "upc", "gtin"}:
        return (got == exp, "IDENTITY_VALUE_MATCH" if got == exp else f"IDENTITY_EVIDENCE_CONFLICT:{canonical}")

    if canonical == "brand":
        # The initial brand can itself be merchant/organization contamination. An explicit
        # product-brand value is allowed to repair it only when that value is present in the
        # product's own model/name text; arbitrary unrelated brands remain blocked.
        compatible = got == exp or got in exp or exp in got or _identity_token_supported(str(value), identity)
        return (compatible, "IDENTITY_VALUE_MATCH" if compatible else "IDENTITY_EVIDENCE_CONFLICT:brand")

    compatible = exp in got or got in exp
    return (compatible, "IDENTITY_VALUE_MATCH" if compatible else "IDENTITY_EVIDENCE_CONFLICT:model")


def _explicit_identity_value(clean: list[Evidence], canonical: str, identity: ProductIdentity) -> str | None:
    candidates: list[Evidence] = []
    for ev in clean:
        if canonical_key(ev.attribute) != canonical:
            continue
        if str(ev.match_level or "").upper() != "EXACT":
            continue
        value = str(ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value or "").strip()
        if not value or not _identity_token_supported(value, identity):
            continue
        candidates.append(ev)
    if not candidates:
        return None
    candidates.sort(key=lambda ev: float(ev.confidence or 0), reverse=True)
    top_value = str(candidates[0].normalized_value if candidates[0].normalized_value not in (None, "") else candidates[0].raw_value)
    competing = {
        key_norm(str(ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value))
        for ev in candidates
    }
    return top_value if len(competing) == 1 else None


def _reconcile_identity(identity: ProductIdentity, specs: dict, clean: list[Evidence]) -> ProductIdentity:
    brand_spec = (specs.get("brand") or {}).get("value")
    explicit_brand = _explicit_identity_value(clean, "brand", identity)
    brand_value = brand_spec or explicit_brand
    if brand_value:
        if not identity.brand or not _identity_token_supported(identity.brand, identity):
            identity.brand = str(brand_value)
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
        canonical = canonical_key(ev.attribute)
        if canonical:
            identity_ok, identity_reason = _identity_bound_evidence_ok(canonical, ev, identity)
            if not identity_ok:
                rejected.append({"attribute": ev.attribute, "value": ev.raw_value, "reason": identity_reason, "source": ev.source_url})
                continue
            semantic_ok, semantic_reason = strict_semantic_gate(canonical, ev)
            if not semantic_ok:
                additional.setdefault(ev.attribute, []).append(ev)
                rejected.append({"attribute": ev.attribute, "value": ev.raw_value, "reason": semantic_reason, "source": ev.source_url})
                continue
            clean.append(ev)
            authority, capped_quality = effective_quality(canonical, ev, quality)
            grouped[canonical].append((ev, capped_quality, authority))
        else:
            clean.append(ev)
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
            rejected.append({"attribute": key, "value": None, "reason": consensus.reason, "source": None})
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

    identity = _reconcile_identity(identity, specs, clean)
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
