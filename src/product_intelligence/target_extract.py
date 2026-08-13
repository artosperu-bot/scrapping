from __future__ import annotations

import re
from rapidfuzz import fuzz
from .models import Evidence
from .normalize import key_norm
from .pdf_attribute_alignment import labels_compatible


def _phrase(value: str) -> str:
    value=re.sub(r'([a-z0-9])([A-Z])',r'\1 \2',str(value or ''))
    value=value.replace('_',' ').replace('-',' ')
    return key_norm(value)


def extract_target_evidence(text: str, targets: list[str] | None, source_url: str, source_type: str,
                            match_level: str, confidence: float) -> list[Evidence]:
    """Extract label/value evidence only for fields the Excel explicitly asks for.

    PDF sources additionally use the generic document-label alignment vocabulary. HTML behavior
    remains unchanged so existing page extraction keeps its established precision contract.
    """
    wanted=[(str(t),_phrase(str(t))) for t in (targets or []) if len(_phrase(str(t)))>=3]
    if not wanted:
        return []
    lines=[re.sub(r'\s+',' ',x).strip() for x in (text or '').splitlines() if x.strip()]
    out=[]; seen=set(); is_pdf='pdf' in str(source_type or '').lower()
    for i,line in enumerate(lines):
        m=re.match(r'^(.{2,120}?)(?:\s*[:=]\s+|\s{2,})(.{1,300})$',line)
        left=m.group(1).strip() if m else line
        right=m.group(2).strip() if m else None
        nl=_phrase(left)
        for original,target in wanted:
            score=fuzz.ratio(nl,target)/100
            contained=(target in nl or nl in target) and min(len(nl),len(target))>=4
            semantic_pdf=is_pdf and labels_compatible(original,left)
            if score < .86 and not contained and not semantic_pdf:
                continue
            value=right
            selector='target_pdf_alias' if semantic_pdf and score < .86 and not contained else 'target_label_value'
            if not value and (score>=.94 or semantic_pdf) and i+1<len(lines):
                nxt=lines[i+1]
                if len(nxt)<=300 and not re.fullmatch(r'[\w áéíóúñÁÉÍÓÚÑ()/#.-]{2,80}:?',nxt):
                    value=nxt; selector='target_next_line'
                elif re.search(r'\d|sí|si|yes|no|true|false|bluetooth|usb|ip\d',nxt,re.I):
                    value=nxt; selector='target_next_line'
            if value in (None,''):
                continue
            key=(key_norm(original),key_norm(value))
            if key in seen: continue
            seen.add(key)
            out.append(Evidence(attribute=original,raw_value=value,normalized_value=value,
                                source_url=source_url,source_type=source_type,selector=selector,
                                match_level=match_level,confidence=min(.97,confidence)))
    return out
