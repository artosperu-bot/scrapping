from __future__ import annotations

import re
from collections import defaultdict

from .evidence_quality import generic_evidence_gate, strict_semantic_gate
from .models import ProductIdentity, ProductRecord, Evidence
from .normalize import canonical_key, key_norm


def _evidence_key(ev: Evidence) -> tuple[str, str, str, str]:
    """A duplicated DOM/JSON rendering is one piece of evidence, not multiple votes."""
    ck=canonical_key(ev.attribute) or key_norm(ev.attribute)
    value=key_norm(str(ev.normalized_value if ev.normalized_value not in (None,"") else ev.raw_value))
    source=str(ev.source_url or "").strip().lower()
    scope=str(ev.match_level or "")
    return ck, value, source, scope


def _identity_token_supported(value: str | None, identity: ProductIdentity) -> bool:
    if not value:
        return False
    needle=key_norm(value).replace(" ","")
    text=key_norm(" ".join(x for x in [identity.product_name, identity.model] if x)).replace(" ","")
    return bool(needle and needle in text)


def _reconcile_identity(identity: ProductIdentity, specs: dict) -> ProductIdentity:
    """Keep seller/organization metadata separate from product identity.

    Explicit canonical product brand/model evidence can repair page-level identity metadata,
    especially on retailer pages where schema Organization is the merchant rather than brand.
    """
    brand_spec=(specs.get("brand") or {}).get("value")
    if brand_spec:
        if not identity.brand or not _identity_token_supported(identity.brand, identity):
            identity.brand=str(brand_spec)
    model_spec=(specs.get("model") or {}).get("value")
    if model_spec and not identity.model:
        identity.model=str(model_spec)
    return identity


def build_record_strict(identity: ProductIdentity, evidence: list[Evidence], sources: list[str]) -> ProductRecord:
    grouped: dict[str, list[tuple[Evidence,float]]] = defaultdict(list)
    additional: dict[str, list[Evidence]] = {}
    clean: list[Evidence] = []
    rejected: list[dict] = []
    seen: set[tuple[str,str,str,str]] = set()
    duplicates=0

    for ev in evidence:
        ok, reason, quality = generic_evidence_gate(ev)
        if not ok:
            rejected.append({"attribute":ev.attribute,"value":ev.raw_value,"reason":reason,"source":ev.source_url})
            continue
        ek=_evidence_key(ev)
        if ek in seen:
            duplicates += 1
            continue
        seen.add(ek)
        clean.append(ev)
        ck = canonical_key(ev.attribute)
        if ck:
            sok, sreason = strict_semantic_gate(ck, ev)
            if not sok:
                additional.setdefault(ev.attribute, []).append(ev)
                rejected.append({"attribute":ev.attribute,"value":ev.raw_value,"reason":sreason,"source":ev.source_url})
                continue
            grouped[ck].append((ev,quality))
        else:
            additional.setdefault(ev.attribute, []).append(ev)

    specs={}
    conflicts=[]
    for key, rows in grouped.items():
        rows.sort(key=lambda x:(x[1], float(x[0].confidence or 0)), reverse=True)
        top,q=rows[0]
        specs[key]={
            "value":top.normalized_value,
            "raw_value":top.raw_value,
            "unit":top.unit,
            "source":top.source_url,
            "source_type":top.source_type,
            "selector":top.selector,
            "confidence":round(min(1.0, q),4),
            "original_confidence":top.confidence,
        }
        # Compare normalized unique values after noise filtering/deduplication. Duplicated HTML,
        # JSON-LD and rendered-DOM copies from one source do not count as corroboration/conflict.
        values: dict[str,list[tuple[Evidence,float]]] = defaultdict(list)
        for e,qv in rows:
            nv=key_norm(str(e.normalized_value if e.normalized_value not in (None,"") else e.raw_value))
            if nv:
                values[nv].append((e,qv))
        if len(values)>1:
            conflict_rows=[]
            for same_value_rows in values.values():
                best=max(same_value_rows,key=lambda x:x[1])
                e,qv=best
                conflict_rows.append({"value":e.normalized_value,"source":e.source_url,"confidence":round(qv,4)})
            conflict_rows.sort(key=lambda x:x["confidence"],reverse=True)
            conflicts.append({"attribute":key,"values":conflict_rows[:12]})

    identity=_reconcile_identity(identity,specs)
    rec=ProductRecord(
        identity=identity,
        specifications=specs,
        additional_attributes=additional,
        evidence=clean,
        sources=list(dict.fromkeys(sources)),
        conflicts=conflicts,
    )
    rec.warnings.append(f"evidence_rejected:{len(rejected)}")
    if duplicates:
        rec.warnings.append(f"evidence_deduplicated:{duplicates}")
    rec.evidence_graph = {"rejected_evidence": rejected[:300], "deduplicated_evidence_count": duplicates}
    return rec
