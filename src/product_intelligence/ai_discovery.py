from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from .ai_enrichment import AIConfig, _json_from_text
from .models import ProductIdentity


@dataclass
class AIDiscoveryCandidate:
    url: str
    country: str | None = None
    confidence: float = 0.0
    reason: str = ""


def _payload(identity: ProductIdentity, country: str) -> str:
    data={k:v for k,v in identity.model_dump().items() if k in {"mpn","ean","upc","gtin","brand","model","product_name","color","variant"} and v not in (None,"")}
    return json.dumps({
        "task":"Find official manufacturer product-page URLs for this exact product. Return JSON only.",
        "preferred_country":country,
        "identity":data,
        "priority":["manufacturer page in preferred country","manufacturer page in nearby/Latin American region","global manufacturer page"],
        "rules":["Search strong identifiers and product name/model","Do not return retailers or marketplaces as official","Return URLs as candidates only; caller validates every page independently"],
        "output":{"candidates":[{"url":"https://example.com/product","country":"PE","confidence":0.95,"reason":"exact identifier on manufacturer page"}]}
    },ensure_ascii=False)


def _openai_text(body: dict[str,Any]) -> str:
    if isinstance(body.get("output_text"),str): return body["output_text"]
    out=[]
    for item in body.get("output") or []:
        for part in item.get("content") or []:
            if isinstance(part.get("text"),str): out.append(part["text"])
    return "\n".join(out)


def _parse(obj: Any) -> list[AIDiscoveryCandidate]:
    rows=(obj or {}).get("candidates",[]) if isinstance(obj,dict) else []
    out=[];seen=set()
    for row in rows:
        if not isinstance(row,dict): continue
        url=str(row.get("url") or "").strip()
        if not url.startswith(("http://","https://")) or url in seen: continue
        if not (urlparse(url).hostname or ""): continue
        seen.add(url)
        try: conf=float(row.get("confidence") or 0)
        except Exception: conf=0
        out.append(AIDiscoveryCandidate(url=url,country=str(row.get("country") or "").strip() or None,confidence=max(0,min(conf,1)),reason=str(row.get("reason") or "")[:400]))
    return out[:12]


def discover_official_urls(identity: ProductIdentity, config: AIConfig | None) -> list[AIDiscoveryCandidate]:
    c=config or AIConfig()
    if not c.enabled or not c.discovery_enabled or not c.model: return []
    prompt=_payload(identity,c.preferred_country or "PE")
    headers={"Content-Type":"application/json"}
    if c.api_key: headers["Authorization"]="Bearer "+c.api_key
    try:
        if c.provider=="openai":
            base=(c.base_url or "https://api.openai.com/v1").rstrip('/')
            r=requests.post(base+"/responses",headers=headers,json={"model":c.model,"tools":[{"type":"web_search"}],"input":prompt},timeout=max(c.timeout,60))
            r.raise_for_status()
            return _parse(_json_from_text(_openai_text(r.json())))
        if c.provider=="openrouter":
            base=(c.base_url or "https://openrouter.ai/api/v1").rstrip('/')
            body={"model":c.model,"messages":[{"role":"system","content":"Return JSON only. Find official product URLs conservatively."},{"role":"user","content":prompt}],"tools":[{"type":"openrouter:web_search","max_total_results":10}],"temperature":0}
            r=requests.post(base+"/chat/completions",headers=headers,json=body,timeout=max(c.timeout,60))
            r.raise_for_status()
            text=(((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "")
            return _parse(_json_from_text(str(text)))
    except Exception:
        return []
    return []
