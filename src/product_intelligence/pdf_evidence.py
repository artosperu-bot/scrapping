from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import ProductIdentity
from .normalize import key_norm
from .web_fetch import UA

_DOCUMENT_HINTS=("pdf","datasheet","data sheet","spec sheet","specification","manual","ficha tecnica","ficha técnica","technical sheet","hoja tecnica","hoja técnica")
_pdf_enabled: ContextVar[bool]=ContextVar("pdf_enabled",default=True)
_pdf_output_root: ContextVar[str|None]=ContextVar("pdf_output_root",default=None)
_pdf_event_sink: ContextVar[object|None]=ContextVar("pdf_event_sink",default=None)

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
    text_hay=_compact(text)
    strong=[x for x in [identity.mpn,identity.ean,identity.upc,identity.gtin] if x]
    brand=_compact(identity.brand)
    model=_compact(identity.model or identity.product_name)
    if strong:
        matched=next((_compact(x) for x in strong if _compact(x) and _compact(x) in hay),None)
        if matched:
            # Once brand identity has been resolved, a direct-discovery PDF must bind
            # the identifier to that brand in its actual content. This prevents an
            # incidental phrase such as "A 2794" in an unrelated document from being
            # accepted as product evidence merely because compact normalization matches.
            if brand:
                if brand in text_hay:
                    return PdfIdentityMatch(True,.99,"strong_identifier_brand")
                if model and model in text_hay and matched in text_hay:
                    return PdfIdentityMatch(True,.94,"strong_identifier_model")
                return PdfIdentityMatch(False,.0,"strong_identifier_without_brand_binding")
            return PdfIdentityMatch(True,.97,"strong_identifier")
        if brand and model and brand in text_hay and model in text_hay:
            return PdfIdentityMatch(True,.92,"brand_model")
        return PdfIdentityMatch(False,.0,"strong_identifier_missing")
    if brand and model and brand in text_hay and model in text_hay:
        return PdfIdentityMatch(True,.92,"brand_model")
    if model and model in text_hay:
        return PdfIdentityMatch(True,.86,"model")
    return PdfIdentityMatch(False,.0,"identity_not_confirmed")

def pdf_evidence_enabled()->bool:
    return bool(_pdf_enabled.get())

def pdf_output_root()->str|None:
    return _pdf_output_root.get()

def emit_pdf_event(stage:str,**payload):
    sink=_pdf_event_sink.get()
    if callable(sink):
        try: sink({"stage":stage,**payload})
        except Exception: pass

@contextmanager
def pdf_evidence_scope(enabled:bool=True,output_root:str|None=None,event_sink=None):
    t1=_pdf_enabled.set(bool(enabled)); t2=_pdf_output_root.set(output_root); t3=_pdf_event_sink.set(event_sink)
    try:
        yield
    finally:
        _pdf_event_sink.reset(t3); _pdf_output_root.reset(t2); _pdf_enabled.reset(t1)

def download_pdf(url:str,destination:str|Path,timeout:int=35)->Path:
    r=requests.get(url,timeout=timeout,headers={"User-Agent":UA,"Accept":"application/pdf,*/*;q=0.8"})
    r.raise_for_status()
    if not is_pdf_payload(r.headers.get("Content-Type"),r.content):
        raise ValueError("La URL no devolvió un PDF válido")
    dest=Path(destination); dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(r.content)
    return dest
