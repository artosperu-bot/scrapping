from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .models import ProductIdentity
from .normalize import key_norm
from .web_fetch import UA

_DOCUMENT_HINTS=("pdf","datasheet","data sheet","spec sheet","specification","manual","ficha tecnica","ficha técnica","technical sheet","hoja tecnica","hoja técnica")
_SOCIAL_TRACKING_HOST_MARKERS=("facebook.com","facebook.net","connect.facebook.net","google-analytics.com","googletagmanager.com","doubleclick.net")
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

def _alpha_skeleton(value:str)->str:
    return re.sub(r"[^a-z]","",key_norm(value or ""))

def _url_has_sibling_model_conflict(model:str|None,url:str)->bool:
    requested=_compact(model)
    if not requested or not any(ch.isdigit() for ch in requested):
        return False
    requested_skeleton=_alpha_skeleton(requested)
    if len(requested_skeleton)<2:
        return False
    for token in re.findall(r"[a-z0-9-]{5,}",str(url or "").lower()):
        compact=_compact(token)
        if compact==requested or not any(ch.isdigit() for ch in compact):
            continue
        if _alpha_skeleton(compact)==requested_skeleton:
            return True
    return False

def _document_link_rejection_reason(url:str,label:str="",source_page_url:str="")->str|None:
    """Reject obvious non-document endpoints before they become PDF candidates.

    The decision is contextual: URL shape, filename, source host and link label are
    considered together. Host markers are only one signal, not the admission rule.
    """
    text=str(url or "").strip()
    if not text:
        return "empty_url"
    parsed=urlparse(text)
    host=(parsed.hostname or "").lower().removeprefix("www.")
    decoded_path=unquote(parsed.path or "")
    filename=decoded_path.rsplit("/",1)[-1].strip()
    if "\\" in decoded_path or "%5c" in text.lower():
        return "malformed_backslash_pdf"
    if filename.lower()==".pdf" or not filename:
        return "empty_pdf_filename"
    source_host=(urlparse(str(source_page_url or "")).hostname or "").lower().removeprefix("www.")
    host_is_tracking=any(host==marker or host.endswith("."+marker) for marker in _SOCIAL_TRACKING_HOST_MARKERS)
    label_norm=key_norm(label or "")
    document_context=any(h in label_norm or h in key_norm(filename) for h in _DOCUMENT_HINTS)
    related_to_source=bool(host and source_host and (host==source_host or host.endswith("."+source_host) or source_host.endswith("."+host)))
    if host_is_tracking and not related_to_source:
        return "social_tracking_endpoint"
    if host_is_tracking and not document_context:
        return "social_tracking_endpoint"
    return None

def discover_pdf_candidates(html:str,base_url:str)->list[PdfCandidate]:
    soup=BeautifulSoup(html or "","lxml")
    out=[]; seen=set()
    for a in soup.find_all("a",href=True):
        href=urljoin(base_url,a.get("href") or "")
        label=a.get_text(" ",strip=True)
        hay=key_norm(f"{label} {href}")
        if ".pdf" not in href.lower() and not any(h in hay for h in _DOCUMENT_HINTS):
            continue
        if _document_link_rejection_reason(href,label,base_url):
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
    model_text=identity.model or identity.product_name
    model=_compact(model_text)
    if strong:
        matched=next((_compact(x) for x in strong if _compact(x) and _compact(x) in hay),None)
        if matched:
            if brand:
                if brand in text_hay:
                    return PdfIdentityMatch(True,.99,"strong_identifier_brand")
                if model and model in text_hay and matched in text_hay:
                    return PdfIdentityMatch(True,.94,"strong_identifier_model")
                return PdfIdentityMatch(False,.0,"strong_identifier_without_brand_binding")
            return PdfIdentityMatch(True,.97,"strong_identifier")
        if brand and model and brand in text_hay and model in text_hay:
            if _url_has_sibling_model_conflict(model_text,url):
                return PdfIdentityMatch(False,.0,"sibling_model_url_conflict")
            return PdfIdentityMatch(True,.92,"brand_model")
        return PdfIdentityMatch(False,.0,"strong_identifier_missing")
    if _url_has_sibling_model_conflict(model_text,url):
        return PdfIdentityMatch(False,.0,"sibling_model_url_conflict")
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