from __future__ import annotations

from dataclasses import dataclass
import requests

from .ai_enrichment import AIConfig


@dataclass
class ModelCapability:
    id: str
    provider: str
    web_discovery: bool
    evidence_enrichment: bool = True
    note: str = ""


DEFAULT_MODELS={
    "openai":["gpt-5-mini-2025-08-07","gpt-5-2025-08-07","gpt-5-nano-2025-08-07","gpt-4.1-mini-2025-04-14"],
    "openrouter":["openai/gpt-5-mini","mistralai/mistral-small","google/gemini-2.5-flash","anthropic/claude-sonnet-4","deepseek/deepseek-chat"],
    "mistral":["mistral-small-latest","mistral-medium-latest","mistral-large-latest"],
    "ollama":["qwen3","mistral","llama3.2"],
    "openai_compatible":[],
}


def capability(provider:str,model:str)->ModelCapability:
    p=(provider or '').lower();m=(model or '').lower()
    if p=="openrouter":
        return ModelCapability(model,p,True,True,"OpenRouter puede añadir web search al modelo seleccionado")
    if p=="openai":
        native=(m.startswith("gpt-5") or m.startswith("gpt-4.1") or m.startswith("o3") or m.startswith("o4"))
        return ModelCapability(model,p,native,True,"web_search nativo" if native else "sin web search configurado")
    if p in {"mistral","ollama","openai_compatible"}:
        return ModelCapability(model,p,False,True,"usable para interpretar evidencia; discovery web requiere OpenAI/OpenRouter")
    return ModelCapability(model,p,False,False,"proveedor desactivado")


def list_models(config:AIConfig)->list[str]:
    p=(config.provider or '').lower()
    base=(config.base_url or '').rstrip('/')
    headers={}
    if config.api_key:headers["Authorization"]="Bearer "+config.api_key
    try:
        if p=="openrouter":
            r=requests.get((base or "https://openrouter.ai/api/v1")+"/models",headers=headers,timeout=20);r.raise_for_status()
            return sorted({str(x.get('id')) for x in r.json().get('data',[]) if x.get('id')})
        if p in {"openai","mistral","openai_compatible"}:
            default={"openai":"https://api.openai.com/v1","mistral":"https://api.mistral.ai/v1"}.get(p,base)
            r=requests.get((base or default)+"/models",headers=headers,timeout=20);r.raise_for_status()
            return sorted({str(x.get('id')) for x in r.json().get('data',[]) if x.get('id')})
        if p=="ollama":
            r=requests.get((base or "http://127.0.0.1:11434")+"/api/tags",timeout=10);r.raise_for_status()
            return sorted({str(x.get('name')) for x in r.json().get('models',[]) if x.get('name')})
    except Exception:
        pass
    return list(DEFAULT_MODELS.get(p,[]))
