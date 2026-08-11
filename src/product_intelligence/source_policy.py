from __future__ import annotations
from urllib.parse import urlparse

MARKETPLACES={
 "falabella.com","falabella.com.pe","ripley.com.pe","mercadolibre.com.pe","amazon.com","amazon.es"
}

def hostname(url:str)->str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")

def is_same_or_subdomain(url:str, official_domain:str)->bool:
    h=hostname(url); d=official_domain.lower().removeprefix("www.")
    return h==d or h.endswith("."+d)

def classify_source(url:str, official_domain:str|None=None)->str:
    h=hostname(url)
    if official_domain and is_same_or_subdomain(url,official_domain): return "manufacturer"
    if any(h==d or h.endswith("."+d) for d in MARKETPLACES): return "marketplace"
    return "secondary"

def allow_technical_source(url:str, official_domain:str|None, allow_secondary:bool=False)->bool:
    t=classify_source(url,official_domain)
    if t=="manufacturer": return True
    if t=="marketplace": return False
    return allow_secondary
