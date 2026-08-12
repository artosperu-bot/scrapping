from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from .attribute_resolver import iter_clean_evidence
from .models import ProductRecord
from .normalize import key_norm


@dataclass
class AIConfig:
    enabled: bool = False
    provider: str = "off"  # off | openai | openrouter | openai_compatible | ollama
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    timeout: int = 45
    max_evidence: int = 70
    discovery_enabled: bool = False
    enrichment_enabled: bool = False
    preferred_country: str = "PE"

    @classmethod
    def from_env(cls) -> "AIConfig":
        provider=os.getenv("PRODUCT_INTEL_AI_PROVIDER","off").strip().lower()
        enabled=provider not in {"","off","none"}
        return cls(
            enabled=enabled,
            provider=provider or "off",
            model=os.getenv("PRODUCT_INTEL_AI_MODEL","").strip(),
            base_url=os.getenv("PRODUCT_INTEL_AI_BASE_URL","").strip(),
            api_key=os.getenv("PRODUCT_INTEL_AI_API_KEY","").strip(),
            discovery_enabled=os.getenv("PRODUCT_INTEL_AI_DISCOVERY","0").strip().lower() in {"1","true","yes","si","sí"},
            enrichment_enabled=os.getenv("PRODUCT_INTEL_AI_ENRICHMENT","0").strip().lower() in {"1","true","yes","si","sí"},
            preferred_country=os.getenv("PRODUCT_INTEL_AI_COUNTRY","PE").strip().upper() or "PE",
        )


def _json_from_text(text: str) -> dict[str,Any] | None:
    text=(text or "").strip()
    if not text:return None
    try:return json.loads(text)
    except Exception:pass
    m=re.search(r"\{.*\}",text,re.S)
    if not m:return None
    try:return json.loads(m.group(0))
    except Exception:return None


def _numeric_tokens(text: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?)*", str(text or "")))


def _evidence_payload(rec:ProductRecord,limit:int=70):
    rows=[]
    for ev,q in iter_clean_evidence(rec):
        raw=ev.normalized_value if ev.normalized_value not in (None,"") else ev.raw_value
        if raw in (None,""):continue
        s=str(raw).strip()
        if not s or len(s)>1200:continue
        rows.append({
            "id":len(rows),
            "attribute":ev.attribute,
            "value":s,
            "source_type":ev.source_type,
            "source":ev.source_url,
            "quality":round(float(q),3),
            "match_level":ev.match_level,
        })
        if len(rows)>=limit:break
    return rows


class AIEnricher:
    """Optional reasoning over already-validated evidence only.

    Web discovery is intentionally separate. This layer cannot browse and cannot become an
    authority for product facts; deterministic guards still validate every proposed value.
    """
    def __init__(self,config:AIConfig|None=None):
        self.config=config or AIConfig.from_env()

    def _call(self,messages:list[dict[str,str]])->dict[str,Any]|None:
        c=self.config
        if not c.enabled or not c.enrichment_enabled or c.provider in {"off","none",""}:return None
        if c.provider=="ollama":
            base=(c.base_url or "http://127.0.0.1:11434").rstrip('/')
            r=requests.post(base+"/api/chat",json={"model":c.model,"messages":messages,"stream":False,"format":"json"},timeout=c.timeout)
            r.raise_for_status()
            return _json_from_text((r.json().get("message") or {}).get("content",""))
        base=(c.base_url or ("https://openrouter.ai/api/v1" if c.provider=="openrouter" else "https://api.openai.com/v1")).rstrip('/')
        headers={"Content-Type":"application/json"}
        if c.api_key:headers["Authorization"]="Bearer "+c.api_key
        payload={"model":c.model,"messages":messages,"temperature":0}
        r=requests.post(base+"/chat/completions",headers=headers,json=payload,timeout=c.timeout)
        r.raise_for_status()
        body=r.json();content=((body.get("choices") or [{}])[0].get("message") or {}).get("content","")
        return _json_from_text(content)

    def suggest(self,rec:ProductRecord,field_label:str,field_description:str|None=None,options:list[Any]|None=None,language:str="es")->dict[str,Any]|None:
        if rec.identity.match_level in {"CONFLICT","LOW"}:return None
        evidence=_evidence_payload(rec,self.config.max_evidence)
        if not evidence:return None
        allowed=[str(x) for x in (options or []) if x not in (None,"")]
        identity=rec.identity.model_dump()
        prompt={
            "task":"Fill exactly one marketplace field using ONLY supplied product evidence.",
            "field":field_label,
            "field_description":field_description or "",
            "output_language":language,
            "identity":identity,
            "allowed_options":allowed,
            "evidence":evidence,
            "rules":[
                "Never use outside knowledge.",
                "Never infer a different variant, color, capacity, MPN, EAN, UPC or GTIN.",
                "If evidence is insufficient or ambiguous, value must be null.",
                "For allowed_options, value must be one exact option or a comma-separated set of exact options.",
                "For descriptions, synthesize only facts explicitly present in evidence; do not add marketing claims or numbers.",
                "Return the ids of every evidence item used.",
            ],
            "output_schema":{"value":"string|null","evidence_ids":[0],"confidence":0.0,"reason":"short string"}
        }
        messages=[
            {"role":"system","content":"You are a conservative catalog data mapper. Output JSON only. Missing is better than wrong."},
            {"role":"user","content":json.dumps(prompt,ensure_ascii=False)}
        ]
        try:ans=self._call(messages)
        except Exception:return None
        if not isinstance(ans,dict) or ans.get("value") in (None,""):return None
        ids=ans.get("evidence_ids") or []
        if not isinstance(ids,list) or not ids:return None
        good_ids=[]
        for x in ids:
            try:i=int(x)
            except Exception:continue
            if 0<=i<len(evidence):good_ids.append(i)
        if not good_ids:return None
        value=str(ans.get("value")).strip()
        if allowed:
            exact={key_norm(x):x for x in allowed}
            parts=[p.strip() for p in re.split(r"[,;|]",value) if p.strip()]
            mapped=[]
            for p in parts:
                if key_norm(p) not in exact:return None
                mapped.append(exact[key_norm(p)])
            value=", ".join(dict.fromkeys(mapped))
        source_text=" ".join(evidence[i]["value"] for i in good_ids)+" "+json.dumps(identity,ensure_ascii=False)
        if not _numeric_tokens(value).issubset(_numeric_tokens(source_text)):
            return None
        conf=float(ans.get("confidence") or 0)
        return {"value":value,"confidence":min(max(conf,0),0.97),"reason":"ai_evidence_grounded:"+str(ans.get("reason") or ""),"evidence_ids":good_ids,"evidence":[evidence[i] for i in good_ids]}
