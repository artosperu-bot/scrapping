from __future__ import annotations

import base64
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from .models import ProductIdentity
from .normalize import key_norm
from .universal_resolution_policy import ResolutionBudget, SearchBudgetTracker

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
SEARCH_PROVIDER_DOMAINS={"google.com","bing.com","duckduckgo.com","brave.com","mojeek.com","yahoo.com"}
MARKETPLACE_HINTS={"amazon.","ebay.","mercadolibre.","falabella.","ripley.","walmart.","bestbuy."}
SEARCH_PROVIDER_WORKERS=6

@dataclass
class SearchCandidate:
    url:str
    title:str=""
    snippet:str=""
    score:float=0.0
    likely_official:bool=False


def build_query(i:ProductIdentity)->str:
    parts=[]
    for v in [i.mpn,i.ean,i.upc,i.gtin,i.sku]:
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


def _unwrap_bing(href:str)->str:
    try:
        parsed=urlparse(str(href or ""))
        host=(parsed.hostname or "").lower()
        if not (host=="bing.com" or host.endswith(".bing.com")) or "/ck/a" not in parsed.path:
            return href
        raw=(parse_qs(parsed.query).get("u") or [""])[0]
        if not raw:return href
        if raw.startswith("a1"):
            payload=raw[2:]; payload += "=" * (-len(payload) % 4)
            decoded=base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8",errors="replace")
            if decoded.startswith(("http://","https://")):return decoded
        decoded=unquote(raw)
        if decoded.startswith(("http://","https://")):return decoded
    except Exception:pass
    return href


def _unwrap_yahoo(href:str)->str:
    m=re.search(r"/RU=([^/]+)/RK=",href)
    return unquote(m.group(1)) if m else href


def _search_ddg(q:str,timeout:int)->list[tuple[str,str,str]]:
    rows=[]
    try:
        r=requests.get("https://html.duckduckgo.com/html/",params={"q":q},headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"},timeout=timeout)
        if r.ok:
            soup=BeautifulSoup(r.text,"lxml")
            for a in soup.select("a.result__a"):
                u=_unwrap_ddg(a.get("href") or "")
                if not u.startswith("http"):continue
                parent=a.find_parent(class_="result"); node=parent.select_one(".result__snippet") if parent else None
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
                u=_unwrap_bing(a.get("href") or "")
                if not u.startswith("http"):continue
                host=(urlparse(u).hostname or "").lower()
                if _is_search_provider_host(host):continue
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
            u=_unwrap_bing((item.findtext("link") or "").strip())
            if not u.startswith("http"):continue
            host=(urlparse(u).hostname or "").lower()
            if _is_search_provider_host(host):continue
            title=(item.findtext("title") or "").strip(); raw=(item.findtext("description") or "").strip()
            rows.append((u,title,BeautifulSoup(raw,"html.parser").get_text(" ",strip=True)))
    except (requests.RequestException,ET.ParseError):pass
    return rows


def _generic_search(url:str,param:str,q:str,timeout:int,selectors:list[str],unwrap=lambda x:x)->list[tuple[str,str,str]]:
    rows=[]
    try:
        r=requests.get(url,params={param:q},headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"},timeout=timeout)
        if not r.ok:return rows
        soup=BeautifulSoup(r.text,"lxml"); anchors=[]
        for sel in selectors:anchors.extend(soup.select(sel))
        if not anchors:anchors=soup.select("a[href]")
        seen=set()
        for a in anchors:
            href=unwrap(a.get("href") or "")
            if not href.startswith("http") or href in seen:continue
            seen.add(href); host=(urlparse(href).hostname or "").lower()
            if _is_search_provider_host(host):continue
            parent=a.find_parent(["article","li","div"]); title=a.get_text(" ",strip=True)
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


def _compact(value:str)->str:return re.sub(r"[^a-z0-9]","",key_norm(value))
def _contains_strong_identifier(text:str,strong:list[str])->bool:
    compact=_compact(text); return any(_compact(x) and _compact(x) in compact for x in strong)


def _descriptive_model(identity:ProductIdentity)->str:
    strong={_compact(str(x)) for x in [identity.mpn,identity.ean,identity.upc,identity.gtin,identity.sku] if x}
    for value in [identity.model,identity.product_name]:
        text=str(value or "").strip()
        if text and _compact(text) not in strong:return key_norm(text)
    return key_norm(identity.model or identity.product_name or "")


def _provider_search(query:str,timeout:int)->list[tuple[str,str,str]]:
    providers=(_search_ddg,_search_bing,_search_bing_rss,_search_brave,_search_mojeek,_search_yahoo)
    workers=max(1,min(SEARCH_PROVIDER_WORKERS,len(providers)))
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix="search-provider") as pool:
        batches=list(pool.map(lambda fn: fn(query,timeout),providers))
    rows=[]
    for batch in batches:rows.extend(batch)
    return rows


def _rank_candidates(urls:list[tuple[str,str,str]], identity:ProductIdentity, limit:int)->list[SearchCandidate]:
    seen=set();out=[];brand=key_norm(identity.brand or "").replace(" ","")
    strong=[str(x) for x in [identity.mpn,identity.ean,identity.upc,identity.gtin,identity.sku] if x]
    model=_descriptive_model(identity)
    technical_terms=("specification","specifications","specs","datasheet","data sheet","manual","support","product page","ficha tecnica","ficha técnica")
    for u,t,sn in urls:
        if u in seen:continue
        seen.add(u); host=(urlparse(u).hostname or "").lower()
        if not host or _is_search_provider_host(host):continue
        combined=f"{u} {t} {sn}"; hay=key_norm(combined); hcompact=re.sub(r"[^a-z0-9]","",host)
        likely_official=bool(brand and brand in hcompact and not any(m in host for m in MARKETPLACE_HINTS))
        strong_match=bool(strong and _contains_strong_identifier(combined,strong)); model_match=bool(model and fuzz_contains(model,hay))
        if strong and not strong_match and not (likely_official and model_match):continue
        score=(.45 if likely_official else 0)+(.38 if strong_match else 0)+(.18 if model_match else 0)
        if any(term in hay for term in technical_terms):score+=.08
        if any(m in host for m in MARKETPLACE_HINTS):score-=.18
        out.append(SearchCandidate(u,t,sn,score,likely_official))
    out.sort(key=lambda x:x.score,reverse=True)
    return out[:limit]


def _merge_ranked(groups:list[list[SearchCandidate]],limit:int)->list[SearchCandidate]:
    best:dict[str,SearchCandidate]={}
    for group in groups:
        for row in group:
            prev=best.get(row.url)
            if prev is None or row.score>prev.score:best[row.url]=row
    return sorted(best.values(),key=lambda x:x.score,reverse=True)[:limit]


def _provider_rows_for_domain(rows:list[tuple[str,str,str]],required_domain:str|None)->list[tuple[str,str,str]]:
    domain=str(required_domain or "").lower().removeprefix("www.").strip()
    if not domain:return rows
    out=[]
    for row in rows:
        host=(urlparse(row[0]).hostname or "").lower().removeprefix("www.")
        if host==domain or host.endswith("."+domain):out.append(row)
    return out


def _budgeted_query(identity:ProductIdentity,query:str,timeout:int,tracker:SearchBudgetTracker,required_domain:str|None=None,on_metrics=None)->list[SearchCandidate]:
    if not query or not tracker.reserve_query():
        if on_metrics:
            on_metrics({"query":str(query or "").strip(),"raw_results":0,"domain_results":0,"valid_results":0})
        return []
    raw_rows=_provider_search(query,timeout)
    domain_rows=_provider_rows_for_domain(raw_rows,required_domain)
    ranked=_rank_candidates(domain_rows,identity,tracker.budget.max_candidates_per_query)
    tracker.admit_candidates(len(ranked))
    if on_metrics:
        on_metrics({"query":query,"raw_results":len(raw_rows),"domain_results":len(domain_rows),"valid_results":len(ranked)})
    return ranked


def search_web_query(identity:ProductIdentity,query:str,limit:int=6,timeout:int=8,budget_tracker:SearchBudgetTracker|None=None,required_domain:str|None=None,on_metrics=None)->list[str]:
    clean=str(query or "").strip()
    if not clean:
        if on_metrics:on_metrics({"query":"","raw_results":0,"domain_results":0,"valid_results":0})
        return []
    if budget_tracker is not None:
        ranked=_budgeted_query(identity,clean,timeout,budget_tracker,required_domain=required_domain,on_metrics=on_metrics)
        return [row.url for row in ranked[:limit]]
    raw_rows=_provider_search(clean,timeout)
    domain_rows=_provider_rows_for_domain(raw_rows,required_domain)
    ranked=_rank_candidates(domain_rows,identity,max(limit*2,limit))
    visible=ranked[:limit]
    if on_metrics:
        on_metrics({"query":clean,"raw_results":len(raw_rows),"domain_results":len(domain_rows),"valid_results":len(visible)})
    return [row.url for row in visible]


def _bootstrap_unknown_identity(identity:ProductIdentity,timeout:int):
    if identity.brand:return identity,None
    try:
        from .identity_bootstrap import bootstrap_identity
        result=bootstrap_identity(identity,limit_per_query=14,timeout=max(5,min(timeout,8)))
        if result.status=="RESOLVED" and result.identity.brand:return result.identity,result.official_domain_hint
    except Exception:pass
    return identity,None


def _tracked_query_plan(identity:ProductIdentity,official_hint:str|None)->list[str]:
    q=build_query(identity)
    if not q:return []
    strong_raw=next((x for x in [identity.mpn,identity.ean,identity.upc,identity.gtin,identity.sku] if x),None)
    brand=str(identity.brand or "").strip(); plan=[]
    def add(value):
        text=str(value or "").strip()
        if text and text not in plan:plan.append(text)
    add(q); add(strong_raw)
    if brand:
        try:
            from .identity_bootstrap import build_deep_queries
            for value in build_deep_queries(identity,official_hint)[:3]:add(value)
        except Exception:pass
    if strong_raw and brand:
        strong=str(strong_raw).strip()
        for value in [f'"{strong}" "{brand}" official product',f'"{strong}" "{brand}" specifications',f'"{strong}" "{brand}" support']:
            add(value)
        descriptive=_descriptive_model(identity)
        if descriptive:add(f'"{descriptive}" "{brand}" official product')
    if strong_raw:
        strong=str(strong_raw).strip()
        for value in [f'"{strong}" product',f'{strong} specifications',f'{strong} manual pdf']:add(value)
    return plan


def search_web(identity:ProductIdentity,limit:int=12,timeout:int=10,budget_tracker:SearchBudgetTracker|None=None,query_quota:int|None=None)->list[SearchCandidate]:
    if budget_tracker is not None:
        # Do not invoke the legacy bootstrap here because it performs hidden web
        # queries outside this shared budget. Search the strongest supplied
        # identity first; later refinement stages may use the reserved budget.
        effective_identity,official_hint=(identity,None) if not identity.brand else (identity,None)
        plan=_tracked_query_plan(effective_identity,official_hint)
        quota=max(0,int(query_quota if query_quota is not None else budget_tracker.remaining_queries()))
        groups=[]
        for query in plan[:quota]:
            if budget_tracker.remaining_queries()<=0:break
            groups.append(_budgeted_query(effective_identity,query,max(6,min(timeout,10)),budget_tracker))
        return _merge_ranked(groups,min(limit,budget_tracker.budget.max_candidates_per_query*max(1,len(groups))))

    effective_identity,official_hint=_bootstrap_unknown_identity(identity,timeout)
    q=build_query(effective_identity)
    if not q:return []
    strong_raw=next((x for x in [effective_identity.mpn,effective_identity.ean,effective_identity.upc,effective_identity.gtin,effective_identity.sku] if x),None)
    queries=[]
    for candidate in [q,str(strong_raw or '').strip()]:
        if candidate and candidate not in queries:queries.append(candidate)
    urls=[]
    for query in queries[:2]:urls.extend(_provider_search(query,max(6,min(timeout,10))))
    ranked=_rank_candidates(urls,effective_identity,limit)
    brand=str(effective_identity.brand or '').strip()
    if brand:
        from .identity_bootstrap import build_deep_queries
        for dq in build_deep_queries(effective_identity,official_hint)[:3]:urls.extend(_provider_search(dq,max(6,min(timeout,10))))
        ranked=_rank_candidates(urls,effective_identity,limit)
    if strong_raw and brand and not any(c.likely_official for c in ranked):
        strong=str(strong_raw).strip(); official_queries=[f'"{strong}" "{brand}" official product',f'"{strong}" "{brand}" specifications',f'"{strong}" "{brand}" support']
        descriptive=_descriptive_model(effective_identity)
        if descriptive:official_queries.append(f'"{descriptive}" "{brand}" official product')
        for oq in official_queries[:3]:
            urls.extend(_provider_search(oq,max(6,min(timeout,10)))); reranked=_rank_candidates(urls,effective_identity,limit)
            if any(c.likely_official for c in reranked):ranked=reranked;break
        else:ranked=_rank_candidates(urls,effective_identity,limit)
    if ranked:return ranked
    if strong_raw:
        strong=str(strong_raw).strip()
        for attempt,query in enumerate([f'"{strong}" product',f'{strong} specifications',f'{strong} manual pdf'][:3]):
            if attempt:time.sleep(.15)
            urls.extend(_provider_search(query,max(6,min(timeout,10)))); ranked=_rank_candidates(urls,effective_identity,limit)
            if ranked:return ranked
    return []


def _field_search_terms(field:str)->list[str]:
    cleaned=re.sub(r"#\s*[A-Za-z]*\d+","",str(field)).strip()
    if not cleaned:return []
    n=key_norm(cleaned); terms=[cleaned]
    if any(x in n for x in ["anofabricacion","ano fabricacion","año fabricacion","release year","launch year","year of release"]):terms.extend(["release date","release year","launch date","official announcement"])
    if any(x in n for x in ["package contents","contenido del paquete"]):terms.extend(["what's in the box","box contents"])
    if any(x in n for x in ["package weight","peso del paquete"]):terms.extend(["package weight","shipping weight"])
    return list(dict.fromkeys(terms))


def _source_query_hint(source_kind:str|None, category:str|None)->str:
    kind=str(source_kind or "").strip().upper(); cat=str(category or "").strip().upper()
    if kind=="MANUFACTURER_SUPPORT":return "official support"
    if kind=="MANUFACTURER":return "official manufacturer"
    if kind=="PRODUCT_CONTENT":return "structured product specifications"
    if kind=="AUTHORIZED_DISTRIBUTOR":return "authorized distributor"
    if kind=="CATEGORY_PROVIDER":
        if cat=="ELECTRONIC_COMPONENT":return "component datasheet technical distributor"
        if cat=="PC_COMPONENT":return "component specifications technical distributor"
        return "technical product data provider"
    return ""


def search_web_for_fields(identity:ProductIdentity,fields:list[str],limit:int=12,timeout:int=10,budget_tracker:SearchBudgetTracker|None=None,query_quota:int|None=None,source_kind:str|None=None,category:str|None=None)->list[SearchCandidate]:
    base=build_query(identity)
    if not base:return []
    terms=[]
    for field in fields or []:
        for term in _field_search_terms(str(field)):
            if term and term not in terms:terms.append(term)
    queries=[];hint=_source_query_hint(source_kind,category)
    for field in terms[:6]:
        candidates=[]
        if hint:
            candidates.extend([f'{base} "{field}" {hint}',f'{base} "{field}" specifications {hint}'])
        candidates.extend([f'{base} "{field}"',f'{base} "{field}" specifications'])
        for query in candidates:
            if query not in queries:queries.append(query)
    if budget_tracker is not None:
        quota=max(0,int(query_quota if query_quota is not None else budget_tracker.remaining_queries()))
        groups=[]
        for query in queries[:quota]:
            if budget_tracker.remaining_queries()<=0:break
            groups.append(_budgeted_query(identity,query,max(6,min(timeout,10)),budget_tracker))
        return _merge_ranked(groups,min(limit,budget_tracker.budget.max_candidates_per_query*max(1,len(groups))))
    urls=[]
    for query in queries:urls.extend(_provider_search(query,max(6,min(timeout,10))))
    return _rank_candidates(urls,identity,limit)


def fuzz_contains(needle:str,hay:str)->bool:
    toks=[x for x in needle.split() if len(x)>=3]
    return bool(toks) and sum(1 for x in toks if x in hay)>=max(1,len(toks)-1)
