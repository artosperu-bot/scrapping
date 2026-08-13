from __future__ import annotations

import re
from rapidfuzz import fuzz

from .models import Evidence
from .normalize import ALIASES, canonical_key, key_norm

_EXTRA_ALIASES={
    "battery_life":["playback time","music playback time","tiempo de reproduccion","tiempo de reproducción","tiempo de reproduccion de musica","tiempo de reproducción de música"],
    "battery_capacity":["battery capacity","capacidad de bateria","capacidad de batería"],
    "weight":["product weight","peso del producto","net weight","peso neto"],
    "dimensions":["product dimensions","dimensiones del producto","size","medidas"],
    "interface":["wireless connection","conexion inalambrica","conexión inalámbrica","connectivity"],
}

def _phrase(value:str)->str:
    return key_norm(str(value or "").replace("_"," ").replace("-"," "))

def _semantic_terms(label:str)->set[str]:
    can=canonical_key(label)
    terms={_phrase(label)}
    if can:
        terms.add(_phrase(can))
        terms.update(_phrase(x) for x in ALIASES.get(can,[]))
        terms.update(_phrase(x) for x in _EXTRA_ALIASES.get(can,[]))
    else:
        nl=_phrase(label)
        for key,vals in _EXTRA_ALIASES.items():
            all_terms=[key,*ALIASES.get(key,[]),*vals]
            if any(nl==_phrase(x) for x in all_terms):
                terms.update(_phrase(x) for x in all_terms)
    return {x for x in terms if x}

def labels_compatible(requested:str,document_label:str)->bool:
    a=_semantic_terms(requested); b=_semantic_terms(document_label)
    if a & b: return True
    return max((fuzz.ratio(x,y)/100 for x in a for y in b),default=0)>=.90

def _pairs(text:str):
    for line in (text or "").splitlines():
        line=re.sub(r"\s+"," ",line).strip(" •\t")
        m=re.match(r"^(.{2,120}?)\s*:\s*(.{1,300})$",line)
        if m: yield m.group(1).strip(),m.group(2).strip()

def align_pdf_attributes(pages,requested_attributes:list[str],source_url:str,local_path:str)->list[Evidence]:
    out=[]; seen=set()
    for page in pages:
        for label,value in _pairs(page.text):
            for requested in requested_attributes or []:
                if not labels_compatible(requested,label): continue
                key=(key_norm(requested),key_norm(value))
                if key in seen: continue
                seen.add(key)
                out.append(Evidence(
                    attribute=requested,raw_value=value,normalized_value=value,
                    source_url=source_url,source_type="pdf",page=int(page.page),
                    selector=f"pdf_path={local_path};method={page.method};label={label}",
                    match_level="HIGH",confidence=.90,
                ))
    return out
