from pathlib import Path

root=Path(__file__).resolve().parents[2]
pkg=root/'src/product_intelligence'

resolution = r'''from __future__ import annotations
import re
from typing import Any
from rapidfuzz import fuzz
from .models import ProductRecord
from .normalize import key_norm

FOUND_DIRECT="FOUND_DIRECT"
FOUND_DERIVED="FOUND_DERIVED"
FOUND_MAPPED="FOUND_MAPPED"
FOUND_CLASSIFIED="FOUND_CLASSIFIED"
SELLER_REQUIRED="SELLER_REQUIRED"
NOT_APPLICABLE="NOT_APPLICABLE"
NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS="NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS"
INSUFFICIENT_EVIDENCE="INSUFFICIENT_EVIDENCE"
CONFLICTING_EVIDENCE="CONFLICTING_EVIDENCE"
FINAL_STATES={FOUND_DIRECT,FOUND_DERIVED,FOUND_MAPPED,FOUND_CLASSIFIED,SELLER_REQUIRED,NOT_APPLICABLE,NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS,INSUFFICIENT_EVIDENCE,CONFLICTING_EVIDENCE}

def _phrase(value:Any)->str:
    value=re.sub(r"([a-z0-9])([A-Z])",r"\1 \2",str(value or ""))
    return key_norm(value.replace("_"," ").replace("-"," "))

def _evidence_text(rec:ProductRecord)->str:
    parts=[f"{e.attribute} {e.raw_value} {e.normalized_value}" for e in rec.evidence]
    parts += [str(v) for v in [rec.identity.product_name,rec.identity.model,rec.identity.brand] if v]
    return key_norm("\n".join(parts))

def _semantic_has_direct_evidence(rec:ProductRecord,semantic:str)->bool:
    target=_phrase(semantic)
    if len(target)<3:return False
    for ev in rec.evidence:
        attr=_phrase(ev.attribute)
        if not attr:continue
        score=fuzz.ratio(attr,target)/100
        contained=(target in attr or attr in target) and min(len(attr),len(target))>=4
        if (score>=.88 or contained) and float(ev.confidence or 0)>=.70:return True
    return False

def _not_applicable(rec:ProductRecord,semantic:str)->tuple[bool,str]:
    s=_phrase(semantic);text=_evidence_text(rec)
    if any(x in s for x in ["autonomia","battery life","play time","runtime"]):
        wired=bool(re.search(r"\bwired\b|cableado|al[aá]mbric|usb[ -]?c wired",text,re.I))
        no_battery=bool(re.search(r"no battery|without battery|sin bater[ií]a|battery required\s*[:=]?\s*(no|false)",text,re.I))
        if wired and no_battery:return True,"wired_product_without_battery"
    return False,""

def cross_field_issues(rec:ProductRecord)->list[dict[str,Any]]:
    text=_evidence_text(rec);issues=[]
    explicit_bt_no=bool(re.search(r"bluetooth[^\n:]{0,40}(?:[:=]|\bis\b)?\s*(no|false|not supported)",text,re.I))
    explicit_bt_yes=bool(re.search(r"bluetooth\s*(?:version|v)?\s*\d|bluetooth[^\n:]{0,30}(yes|true|supported)",text,re.I))
    if explicit_bt_no and explicit_bt_yes:issues.append({"code":"BLUETOOTH_CONTRADICTION","severity":"BLOCK","message":"Bluetooth contradictorio."})
    wired=bool(re.search(r"\bwired\b|cableado|al[aá]mbric",text,re.I))
    no_battery=bool(re.search(r"no battery|without battery|sin bater[ií]a",text,re.I))
    autonomy=bool(re.search(r"(?:battery life|play time|autonom[ií]a|runtime)[^\n]{0,80}\b\d+(?:[.,]\d+)?\s*(?:h|hr|hours?|horas?)\b",text,re.I))
    if wired and no_battery and autonomy:issues.append({"code":"WIRED_AUTONOMY_CONTRADICTION","severity":"BLOCK","message":"Autonomía incompatible con producto cableado/sin batería."})
    return issues

def analyze_resolution(rec:ProductRecord,template_plan:dict|None)->dict[str,Any]:
    semantics=list(dict.fromkeys(str(x) for x in ((template_plan or {}).get("scrape_semantics") or []) if x))
    conflict_keys={_phrase(c.get("attribute")) for c in (rec.conflicts or []) if c.get("attribute")}
    fields=[];research=[]
    for semantic in semantics:
        s=_phrase(semantic)
        if any(fuzz.ratio(s,c)/100>=.88 for c in conflict_keys if c):status=CONFLICTING_EVIDENCE;reason="multiple_high_quality_values"
        else:
            na,na_reason=_not_applicable(rec,semantic)
            if na:status=NOT_APPLICABLE;reason=na_reason
            elif _semantic_has_direct_evidence(rec,semantic):status=FOUND_DIRECT;reason="validated_evidence_matches_field_semantics"
            else:status=INSUFFICIENT_EVIDENCE;reason="no_validated_evidence_for_requested_semantic";research.append(semantic)
        fields.append({"semantic":semantic,"status":status,"reason":reason})
    issues=cross_field_issues(rec)
    return {"fields":fields,"counts":{state:sum(1 for x in fields if x["status"]==state) for state in FINAL_STATES},"research_terms":research[:6],"cross_field_issues":issues,"blocked":any(x.get("severity")=="BLOCK" for x in issues)}
'''
(pkg/'resolution_engine.py').write_text(resolution,encoding='utf-8')

# discovery: targeted free gap search
p=pkg/'discovery.py';s=p.read_text(encoding='utf-8')
if 'def search_web_for_fields(' not in s:
    s += r'''

def search_web_for_fields(identity:ProductIdentity,fields:list[str],limit:int=12,timeout:int=15)->list[SearchCandidate]:
    """Free second-pass discovery for unresolved workbook semantics; candidates remain untrusted."""
    base=build_query(identity)
    if not base:return []
    terms=[]
    for field in fields or []:
        cleaned=re.sub(r"#\s*[A-Za-z]*\d+","",str(field)).strip()
        if cleaned and cleaned not in terms:terms.append(cleaned)
    urls=[]
    for field in terms[:6]:
        for q in [f'{base} "{field}"',f'{base} "{field}" specifications',f'{base} "{field}" manual datasheet']:
            urls.extend(_provider_search(q,max(8,min(timeout,15))))
    return _rank_candidates(urls,identity,limit)
'''
    p.write_text(s,encoding='utf-8')

# derivations: applicability + technical IP projection
p=pkg/'field_derivations.py';s=p.read_text(encoding='utf-8')
old='''    if best:\n        score,ev,h=best\n        val=f"{int(h) if h.is_integer() else h:g} h"\n        return Derived(val,min(.99,score),"verified_playtime",ev.source_url,ev.attribute,ev.raw_value)\n    return Derived(reason="autonomy_not_found")'''
new='''    if best:\n        score,ev,h=best\n        val=f"{int(h) if h.is_integer() else h:g} h"\n        return Derived(val,min(.99,score),"verified_playtime",ev.source_url,ev.attribute,ev.raw_value)\n    text=key_norm(_all_text(rec))\n    wired=bool(re.search(r"\\bwired\\b|cableado|al[aá]mbric|usb[ -]?c wired",text,re.I))\n    no_battery=bool(re.search(r"no battery|without battery|sin bater[ií]a|battery required\\s*[:=]?\\s*(no|false)",text,re.I))\n    if wired and no_battery:return Derived(reason="NOT_APPLICABLE:wired_product_without_battery")\n    return Derived(reason="INSUFFICIENT_EVIDENCE:autonomy_not_found")'''
if old not in s:raise SystemExit('autonomy anchor not found')
s=s.replace(old,new)
old2="        return Derived(reason=f'ip_rating_{rating}_not_in_allowed_options')"
new2='''        m_full=re.fullmatch(r'IP([0-6])([0-9])',rating,re.I)\n        if m_full:\n            water='IPX'+m_full.group(2);nw=key_norm(water)\n            for no,o in opts.items():\n                if no==nw or no.startswith(nw+' '):\n                    q,ev=src\n                    return Derived(o,min(.98,q+.02),'derived_water_component_from_full_ip_rating',ev.source_url,ev.attribute,ev.raw_value)\n        return Derived(reason=f'NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS:ip_rating_{rating}')'''
if old2 not in s:raise SystemExit('water anchor not found')
s=s.replace(old2,new2)
p.write_text(s,encoding='utf-8')

# batch integration: second pass and audit
p=pkg/'batch.py';s=p.read_text(encoding='utf-8')
s=s.replace('from .discovery import search_web','from .discovery import search_web, search_web_for_fields')
if 'from .resolution_engine import analyze_resolution' not in s:s=s.replace('from .record_builder import build_record_strict','from .record_builder import build_record_strict\nfrom .resolution_engine import analyze_resolution')
anchor='''    rec = _merge_valid_records(accepted)\n    Path(out_dir).mkdir(parents=True, exist_ok=True)'''
replacement='''    rec = _merge_valid_records(accepted)\n    resolution=analyze_resolution(rec,template_plan)\n    gap_terms=list(resolution.get("research_terms") or [])\n    if gap_terms and not resolution.get("blocked"):\n        log(f"  segunda pasada por huecos: {', '.join(gap_terms[:4])}")\n        extra=[]\n        for gc in search_web_for_fields(rec.identity,gap_terms[:4],limit=10):\n            if gc.url in seen_urls or gc.url in set(rec.sources or []):continue\n            seen_urls.add(gc.url)\n            try:\n                host=(urlparse(gc.url).hostname or "").removeprefix("www.")\n                gr=pipe.process_url(item.identity,gc.url,official_domain=host if getattr(gc,"likely_official",False) else None,include_pdfs=include_pdfs,include_images=include_images,browser_fallback=True,target_semantics=gap_terms,media_slots=media_slots)\n                if gr.identity.identifiers_conflicting:continue\n                if accepted and not _cross_source_consistent(accepted[0],gr,gc.url):continue\n                extra.append(gr);log(f"  gap fuente validada: {(gr.fetch or {}).get('source_class','?')} / {gr.identity.match_level}")\n                if len(extra)>=3:break\n            except Exception as exc:errors.append(f"gap:{gc.url}: {type(exc).__name__}: {exc}")\n        if extra:\n            accepted.extend(extra);rec=_merge_valid_records(accepted);resolution=analyze_resolution(rec,template_plan)\n    rec.evidence_graph=dict(rec.evidence_graph or {});rec.evidence_graph["resolution_audit"]=resolution\n    rec.missing_fields=[x["semantic"] for x in resolution.get("fields",[]) if x.get("status")=="INSUFFICIENT_EVIDENCE"]\n    for issue in resolution.get("cross_field_issues",[]):rec.warnings.append(f"cross_field:{issue.get('code')}")\n    Path(out_dir).mkdir(parents=True, exist_ok=True)'''
if anchor not in s:raise SystemExit('batch anchor not found')
s=s.replace(anchor,replacement)
p.write_text(s,encoding='utf-8')

(root/'tests/test_resolution_engine.py').write_text(r'''from product_intelligence.field_derivations import derive_autonomy,derive_water_resistance
from product_intelligence.models import Evidence,ProductIdentity,ProductRecord
from product_intelligence.resolution_engine import analyze_resolution,NOT_APPLICABLE

def _rec(ev):return ProductRecord(identity=ProductIdentity(mpn="X1",match_level="EXACT",confidence=.99),evidence=ev)

def test_ip65_projects_to_ipx5():
    r=_rec([Evidence(attribute="IP rating",raw_value="IP65",normalized_value="IP65",source_type="official_html",match_level="EXACT",confidence=.98)])
    d=derive_water_resistance(r,["No","IPX4","IPX5","IPX7"]);assert d.value=="IPX5"

def test_wired_no_battery_autonomy_not_applicable():
    r=_rec([Evidence(attribute="connection type",raw_value="Wired USB-C",normalized_value="Wired USB-C",source_type="official_html",match_level="EXACT",confidence=.95),Evidence(attribute="battery",raw_value="No battery",normalized_value="No battery",source_type="official_html",match_level="EXACT",confidence=.95)])
    assert derive_autonomy(r).reason.startswith("NOT_APPLICABLE")
    assert analyze_resolution(r,{"scrape_semantics":["Autonomía"]})["fields"][0]["status"]==NOT_APPLICABLE

def test_missing_field_goes_to_gap_research():
    r=_rec([Evidence(attribute="Bluetooth",raw_value="5.3",normalized_value="5.3",source_type="official_html",match_level="EXACT",confidence=.95)])
    a=analyze_resolution(r,{"scrape_semantics":["Bluetooth","Package weight"]})
    assert "Package weight" in a["research_terms"]
''',encoding='utf-8')
