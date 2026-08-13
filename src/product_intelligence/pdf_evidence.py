from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import ProductIdentity
from .normalize import key_norm
from .web_fetch import UA

_DOCUMENT_HINTS=("pdf","datasheet","data sheet","spec sheet","specification","manual","ficha tecnica","ficha técnica","technical sheet","hoja tecnica","hoja técnica")

@dataclass(frozen=True)
class PdfCandidate:
    url:str
    label:str=""
    source_page_url:str=""

@dataclass(frozen=True)
class PdfIdentityMatch:
    accepted:bool
    confidence:float
    reason:str

def _compact(value):
    return re.sub(r"[^a-z0-9]","",key_norm(value or ""))

def discover_pdf_candidates(html:str,base_url:str)->list[PdfCandidate]:
    soup=BeautifulSoup(html or "","lxml")
    out=[]; seen=set()
    for a in soup.find_all("a",href=True):
        href=urljoin(base_url,a.get("href") or "")
        label=a.get_text(" ",strip=True)
        hay=key_norm(f"{label} {href}")
        if ".pdf" not in href.lower() and not any(h in hay for h in _DOCUMENT_HINTS):
            continue
        if href in seen: continue
        seen.add(href); out.append(PdfCandidate(href,label,base_url))
    return out

def is_pdf_payload(content_type:str|None,data:bytes)->bool:
    c=(content_type or "").lower()
    return "application/pdf" in c or bytes(data[:5])==b"%PDF-"

def validate_pdf_identity(identity:ProductIdentity,text:str,url:str="")->PdfIdentityMatch:
    hay=_compact(f"{url} {text}")
    strong=[x for x in [identity.mpn,identity.ean,identity.upc,identity.gtin] if x]
    if strong:
        if any(_compact(x) in hay for x in strong):
            return PdfIdentityMatch(True,.99,"strong_identifier")
        model=_compact(identity.model or identity.product_name)
        brand=_compact(identity.brand)
        if brand and model and brand in hay and model in hay:
            return PdfIdentityMatch(True,.92,"brand_model")
        return PdfIdentityMatch(False,.0,"strong_identifier_missing")
    model=_compact(identity.model or identity.product_name)
    brand=_compact(identity.brand)
    if brand and model and brand in hay and model in hay:
        return PdfIdentityMatch(True,.92,"brand_model")
    if model and model in hay:
        return PdfIdentityMatch(True,.86,"model")
    return PdfIdentityMatch(False,.0,"identity_not_confirmed")

def download_pdf(url:str,destination:str|Path,timeout:int=35)->Path:
    r=requests.get(url,timeout=timeout,headers={"User-Agent":UA,"Accept":"application/pdf,*/*;q=0.8"})
    r.raise_for_status()
    if not is_pdf_payload(r.headers.get("Content-Type"),r.content):
        raise ValueError("La URL no devolvió un PDF válido")
    dest=Path(destination); dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(r.content)
    return dest
