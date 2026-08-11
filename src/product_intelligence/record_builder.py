from __future__ import annotations

from collections import defaultdict

from .evidence_quality import generic_evidence_gate, strict_semantic_gate
from .models import ProductIdentity, ProductRecord, Evidence
from .normalize import canonical_key


def build_record_strict(identity: ProductIdentity, evidence: list[Evidence], sources: list[str]) -> ProductRecord:
    grouped: dict[str, list[tuple[Evidence,float]]] = defaultdict(list)
    additional: dict[str, list[Evidence]] = {}
    clean: list[Evidence] = []
    rejected: list[dict] = []

    for ev in evidence:
        ok, reason, quality = generic_evidence_gate(ev)
        if not ok:
            rejected.append({"attribute":ev.attribute,"value":ev.raw_value,"reason":reason,"source":ev.source_url})
            continue
        clean.append(ev)
        ck = canonical_key(ev.attribute)
        if ck:
            sok, sreason = strict_semantic_gate(ck, ev)
            if not sok:
                # Keep the evidence available under its raw attribute for later template matching,
                # but never let it poison a canonical specification.
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
        vals={str(e.normalized_value).strip().lower() for e,_ in rows if e.normalized_value not in (None,"")}
        if len(vals)>1:
            conflicts.append({"attribute":key,"values":[
                {"value":e.normalized_value,"source":e.source_url,"confidence":round(qv,4)} for e,qv in rows[:12]
            ]})

    rec=ProductRecord(
        identity=identity,
        specifications=specs,
        additional_attributes=additional,
        evidence=clean,
        sources=list(dict.fromkeys(sources)),
        conflicts=conflicts,
    )
    rec.warnings.append(f"evidence_rejected:{len(rejected)}")
    rec.evidence_graph = {"rejected_evidence": rejected[:300]}
    return rec
