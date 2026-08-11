from __future__ import annotations
from typing import Any
from urllib.parse import urlparse


def build_evidence_graph(identity: dict[str, Any], sources: list[str], evidence: list[dict], media: list[dict]) -> dict:
    nodes=[]; edges=[]
    nodes.append({"id":"target","type":"product_identity","data":identity})
    source_ids={}
    for idx,url in enumerate(dict.fromkeys(sources)):
        sid=f"source:{idx}"
        source_ids[url]=sid
        nodes.append({"id":sid,"type":"source","url":url,"host":urlparse(url).hostname})
        edges.append({"from":"target","to":sid,"relation":"validated_source_for"})
    for idx,ev in enumerate(evidence):
        eid=f"evidence:{idx}"
        nodes.append({"id":eid,"type":"attribute_evidence","attribute":ev.get("attribute"),"value":ev.get("normalized_value"),"confidence":ev.get("confidence")})
        src=ev.get("source_url")
        if src in source_ids:
            edges.append({"from":source_ids[src],"to":eid,"relation":"supports"})
        edges.append({"from":eid,"to":"target","relation":"describes"})
    for idx,m in enumerate(media):
        mid=f"media:{idx}"
        nodes.append({"id":mid,"type":"media","url":m.get("url"),"media_type":m.get("media_type"),"scope":m.get("scope"),"confidence":m.get("confidence")})
        edges.append({"from":mid,"to":"target","relation":m.get("scope") or "UNVERIFIED"})
    return {"nodes":nodes,"edges":edges}
