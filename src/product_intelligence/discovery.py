from __future__ import annotations

import html as htmlmod
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from .models import ProductIdentity
from .normalize import key_norm

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
BLOCKED_HOSTS={"google.com","www.google.com","bing.com","www.bing.com","duckduckgo.com","html.duckduckgo.com"}
MARKETPLACE_HINTS={"amazon.","ebay.","mercadolibre.","falabella.","ripley.","walmart.","bestbuy."}

@dataclass
class SearchCandidate:
    url:str
    title:str=""
    snippet:str=""
    score:float=0.0
    likely_official:bool=False


def build_query(i:ProductIdentity)->str:
    parts=[]
    for v in [i.mpn,i.ean,i.upc,i.gtin]:
        if v: parts.append(f'"{v}"')
    for v in [i.brand,i.model,i.product_name]:
        if v and v not in parts: parts.append(str(v))
    return " ".join(parts[:6])


def _unwrap_ddg(href:str)->str:
    if "uddg=" in href:
        qs=parse_qs(urlparse(href).query)
        if qs.get("uddg"): return unquote(qs["uddg"][0])
    return href


def _search_ddg(q:str,timeout:int)->list[tuple[str,str,str]]:
    rows=[]
    try:
        r=requests.get("https://html.duckduckgo.com/html/",params={"q":q},headers={"User-Agent":UA},timeout=timeout)
        if r.ok:
            soup=BeautifulSoup(r.text,"lxml")
            for a in soup.select("a.result__a"):
                u=_unwrap_ddg(a.get("href") or "")
                if not u.startswith("http"): continue
                parent=a.find_parent(class_="result")
                sn=""
                if parent:
                    node=parent.select_one(".result__snippet")
                    sn=node.get_text(" ",strip=True) if node else ""
                rows.append((u,a.get_text(" ",strip=True),sn))
    except Exception:
        pass
    return rows


def _search_bing(q:str,timeout:int)->list[tuple[str,str,str]]:
    """Second discovery backend; candidates are still identity-validated later."""
    rows=[]
    try:
        r=requests.get("https://www.bing.com/search",params={"q":q,"count":20},headers={"User-Agent":UA},timeout=timeout)
        if r.ok:
            soup=BeautifulSoup(r.text,"lxml")
            for li in soup.select("li.b_algo"):
                a=li.select_one("h2 a")
                if not a: continue
                u=a.get("href") or ""
                if not u.startswith("http"): continue
                node=li.select_one(".b_caption p")
                sn=node.get_text(" ",strip=True) if node else ""
                rows.append((u,a.get_text(" ",strip=True),sn))
    except Exception:
        pass
    return rows


def search_web(identity:ProductIdentity, limit:int=12, timeout:int=20)->list[SearchCandidate]:
    q=build_query(identity)
    if not q:return []
    # Use more than one normal public search backend because any single HTML endpoint can fail.
    queries=[q]
    strong_raw=next((x for x in [identity.mpn,identity.ean,identity.upc,identity.gtin] if x),None)
    if strong_raw:
        plain=str(strong_raw).strip()
        if plain and plain not in queries:queries.append(plain)
    urls=[]
    for query in queries:
        urls.extend(_search_ddg(query,timeout))
        urls.extend(_search_bing(query,timeout))
    seen=set();out=[]
    brand=key_norm(identity.brand or "").replace(" ","")
    strong=[key_norm(x) for x in [identity.mpn,identity.ean,identity.upc,identity.gtin] if x]
    model=key_norm(identity.model or identity.product_name or "")
    for u,t,sn in urls:
        if u in seen:continue
        seen.add(u)
        host=(urlparse(u).hostname or "").lower()
        if host in BLOCKED_HOSTS:continue
        hay=key_norm(f"{u} {t} {sn}")
        compact_hay=re.sub(r"[^a-z0-9]","",hay)
        hcompact=re.sub(r"[^a-z0-9]","",host)
        likely_official=bool(brand and brand in hcompact and not any(m in host for m in MARKETPLACE_HINTS))
        score=0.0
        if likely_official:score+=.45
        if strong and any(re.sub(r"[^a-z0-9]","",x) in compact_hay for x in strong):score+=.38
        if model and fuzz_contains(model,hay):score+=.18
        if any(m in host for m in MARKETPLACE_HINTS):score-=.18
        out.append(SearchCandidate(u,t,sn,score,likely_official))
    out.sort(key=lambda x:x.score,reverse=True)
    return out[:limit]


def fuzz_contains(needle:str,hay:str)->bool:
    toks=[x for x in needle.split() if len(x)>=3]
    return bool(toks) and sum(1 for x in toks if x in hay)>=max(1,len(toks)-1)
