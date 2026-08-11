from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from .models import ProductIdentity
from .normalize import key_norm

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
SEARCH_PROVIDER_DOMAINS={"google.com","bing.com","duckduckgo.com","brave.com","mojeek.com","yahoo.com"}
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


def _is_search_provider_host(host:str)->bool:
    host=(host or "").lower().split(":",1)[0]
    return any(host==d or host.endswith("."+d) for d in SEARCH_PROVIDER_DOMAINS)


def _unwrap_ddg(href:str)->str:
    if "uddg=" in href:
        qs=parse_qs(urlparse(href).query)
        if qs.get("uddg"): return unquote(qs["uddg"][0])
    return href


def _unwrap_yahoo(href:str)->str:
    m=re.search(r"/RU=([^/]+)/RK=",href)
    if m:return unquote(m.group(1))
    return href


def _search_ddg(q:str,timeout:int)->list[tuple[str,str,str]]:
    rows=[]
    try:
        r=requests.get("https://html.duckduckgo.com/html/",params={"q":q},headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"},timeout=timeout)
        if r.ok:
            soup=BeautifulSoup(r.text,"lxml")
            for a in soup.select("a.result__a"):
                u=_unwrap_ddg(a.get("href") or "")
                if not u.startswith("http"):continue
                parent=a.find_parent(class_="result")
                node=parent.select_one(".result__snippet") if parent else None
                rows.append((u,a.get_text(" ",strip=True),node.get_text(" ",strip=True) if node else ""))
    except requests.RequestException:pass
    return rows


def _search_bing(q:str,timeout:int)->list[tuple[str,str,str]]:
    rows=[]
    try:
        r=requests.get("https://www.bing.com/search",params={"q":q,"count":20},headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"},timeout=timeout)
        if r.ok:
            soup=BeautifulSoup(r.text,"lxml")
            for li in soup.select("li.b_algo"):
                a=li.select_one("h2 a")
                if not a:continue
                u=a.get("href") or ""
                if not u.startswith("http"):continue
                node=li.select_one(".b_caption p")
                rows.append((u,a.get_text(" ",strip=True),node.get_text(" ",strip=True) if node else ""))
    except requests.RequestException:pass
    return rows


def _search_bing_rss(q:str,timeout:int)->list[tuple[str,str,str]]:
    rows=[]
    try:
        r=requests.get("https://www.bing.com/search",params={"q":q,"format":"rss","count":20},headers={"User-Agent":UA,"Accept":"application/rss+xml,application/xml;q=0.9,text/xml;q=0.8,*/*;q=0.5"},timeout=timeout)
        if not r.ok or not r.content:return rows
        root=ET.fromstring(r.content)
        for item in root.findall(".//item"):
            u=(item.findtext("link") or "").strip()
            if not u.startswith("http"):continue
            title=(item.findtext("title") or "").strip()
            raw=(item.findtext("description") or "").strip()
            rows.append((u,title,BeautifulSoup(raw,"html.parser").get_text(" ",strip=True)))
    except (requests.RequestException,ET.ParseError):pass
    return rows


def _generic_search(url:str,param:str,q:str,timeout:int,selectors:list[str],unwrap=lambda x:x)->list[tuple[str,str,str]]:
    rows=[]
    try:
        r=requests.get(url,params={param:q},headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"},timeout=timeout)
        if not r.ok:return rows
        soup=BeautifulSoup(r.text,"lxml")
        anchors=[]
        for sel in selectors:anchors.extend(soup.select(sel))
        if not anchors:anchors=soup.select("a[href]")
        seen=set()
        for a in anchors:
            href=unwrap(a.get("href") or "")
            if not href.startswith("http") or href in seen:continue
            seen.add(href)
            host=(urlparse(href).hostname or "").lower()
            # Generic fallback parsers can see navigation/login/search links. Never emit
            # any link that still belongs to a search provider, including subdomains.
            if _is_search_provider_host(host):continue
            parent=a.find_parent(["article","li","div"])
            title=a.get_text(" ",strip=True)
            snippet=parent.get_text(" ",strip=True)[:1200] if parent else title
            rows.append((href,title,snippet))
    except requests.RequestException:pass
    return rows


def _search_brave(q:str,timeout:int):
    return _generic_search("https://search.brave.com/search","q",q,timeout,["a[href][data-testid='result-title-a']","div.snippet a[href]","a.result-header[href]"])

def _search_mojeek(q:str,timeout:int):
    return _generic_search("https://www.mojeek.com/search","q",q,timeout,["ul.results-standard h2 a[href]","li.result h2 a[href]","a.ob[href]"])

def _search_yahoo(q:str,timeout:int):
    return _generic_search("https://search.yahoo.com/search","p",q,timeout,["div.algo-sr h3 a[href]","div.algo h3 a[href]","h3.title a[href]"],_unwrap_yahoo)


def _compact(value:str)->str:
    return re.sub(r"[^a-z0-9]","",key_norm(value))

def _contains_strong_identifier(text:str,strong:list[str])->bool:
    compact=_compact(text)
    return any(_compact(x) and _compact(x) in compact for x in strong)


def search_web(identity:ProductIdentity,limit:int=12,timeout:int=20)->list[SearchCandidate]:
    q=build_query(identity)
    if not q:return []
    queries=[q]
    strong_raw=next((x for x in [identity.mpn,identity.ean,identity.upc,identity.gtin] if x),None)
    if strong_raw:
        plain=str(strong_raw).strip()
        if plain and plain not in queries:queries.append(plain)
    urls=[]
    for query in queries:
        urls.extend(_search_ddg(query,timeout));urls.extend(_search_bing(query,timeout));urls.extend(_search_bing_rss(query,timeout))
        urls.extend(_search_brave(query,timeout));urls.extend(_search_mojeek(query,timeout));urls.extend(_search_yahoo(query,timeout))

    seen=set();out=[]
    brand=key_norm(identity.brand or "").replace(" ","")
    strong=[str(x) for x in [identity.mpn,identity.ean,identity.upc,identity.gtin] if x]
    model=key_norm(identity.model or identity.product_name or "")
    for u,t,sn in urls:
        if u in seen:continue
        seen.add(u)
        host=(urlparse(u).hostname or "").lower()
        if not host or _is_search_provider_host(host):continue
        combined=f"{u} {t} {sn}"
        hay=key_norm(combined)
        if strong and not _contains_strong_identifier(combined,strong):continue
        hcompact=re.sub(r"[^a-z0-9]","",host)
        likely_official=bool(brand and brand in hcompact and not any(m in host for m in MARKETPLACE_HINTS))
        score=0.0
        if likely_official:score+=.45
        if strong and _contains_strong_identifier(combined,strong):score+=.38
        if model and fuzz_contains(model,hay):score+=.18
        if any(m in host for m in MARKETPLACE_HINTS):score-=.18
        out.append(SearchCandidate(u,t,sn,score,likely_official))
    out.sort(key=lambda x:x.score,reverse=True)
    return out[:limit]


def fuzz_contains(needle:str,hay:str)->bool:
    toks=[x for x in needle.split() if len(x)>=3]
    return bool(toks) and sum(1 for x in toks if x in hay)>=max(1,len(toks)-1)
