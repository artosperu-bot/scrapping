from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from openpyxl import load_workbook

from .discovery import search_web
from .excel_mapper_v8 import fill_excel_v8
from .ai_enrichment import AIConfig
from .models import ProductIdentity, ProductRecord
from .normalize import key_norm
from .pipeline import ProductPipeline
from .record_builder import build_record_strict
from .template_intelligence import analyze_matrix


@dataclass
class BatchItem:
    row:int
    sheet:str
    identity:ProductIdentity
    source_url:str|None=None


def _clean_id(v):
    if v is None:return None
    s=str(v).strip()
    if s.endswith('.0') and s[:-2].isdigit(): s=s[:-2]
    return s or None


def detect_items(template:str)->list[BatchItem]:
    wb=load_workbook(template,data_only=False,read_only=False)
    items=[]
    for ws in wb.worksheets:
        matrix=[[ws.cell(r,c).value for c in range(1,ws.max_column+1)] for r in range(1,min(ws.max_row,20)+1)]
        info=analyze_matrix(matrix)
        hr=info['header_row']
        fields={f['column']:f for f in info['fields']}
        if not fields: continue
        for r in range(hr+1,ws.max_row+1):
            vals={}
            source_url=None
            for c,f in fields.items():
                v=ws.cell(r,c).value
                lab=key_norm(f['label'])
                can=f.get('canonical')
                if v in (None,''): continue
                if can in {'brand','model','ean','upc','gtin','mpn'}: vals[can]=_clean_id(v)
                if 'sku del vendedor' in lab or 'seller sku' in lab: vals['sku']=_clean_id(v)
                if f.get('external_id')=='39' or can=='product_name': vals['product_name']=str(v).strip()
                if 'source url' in lab or 'url fuente' in lab or 'pagina oficial' in lab: source_url=str(v).strip()
            # Detect explicit Part Number headers even if not canonical in template parser.
            for c in range(1,ws.max_column+1):
                h=str(ws.cell(hr,c).value or '')
                n=key_norm(h)
                if any(x==n or x in n for x in ['mpn','part number','manufacturer part number','codigo fabricante']):
                    vals['mpn']=_clean_id(ws.cell(r,c).value)
            # Seller SKU is not assumed to be MPN. It is only a search hint through product_name/model if no other data.
            if not any(vals.get(k) for k in ['mpn','ean','upc','gtin','model','product_name']): continue
            items.append(BatchItem(r,ws.title,ProductIdentity(**{k:v for k,v in vals.items() if k in ProductIdentity.model_fields}),source_url))
    return items


def _best_product_sheet(template:str)->tuple[str,int]:
    """Return the most likely product upload sheet and its header row."""
    wb=load_workbook(template,data_only=False,read_only=False)
    best=None
    for ws in wb.worksheets:
        matrix=[[ws.cell(r,c).value for c in range(1,ws.max_column+1)] for r in range(1,min(ws.max_row,20)+1)]
        info=analyze_matrix(matrix)
        score=len(info.get('fields') or [])
        if score and (best is None or score>best[0]):
            best=(score,ws.title,info['header_row'])
    if not best:
        raise ValueError('No se pudo detectar la hoja de carga de productos del Excel.')
    return best[1],best[2]


def manual_items(template:str, part_numbers:list[str])->list[BatchItem]:
    """Assign explicit manufacturer part numbers to consecutive product rows.

    This mode is meant for an empty marketplace template: the part number is a
    search identity only and is not silently written into Seller SKU fields.
    """
    sheet,header_row=_best_product_sheet(template)
    clean=[]
    seen=set()
    for pn in part_numbers:
        v=_clean_id(pn)
        if not v: continue
        k=v.upper()
        if k in seen: continue
        seen.add(k);clean.append(v)
    return [BatchItem(header_row+i+1,sheet,ProductIdentity(mpn=pn)) for i,pn in enumerate(clean)]


def scrape_item(item:BatchItem, out_dir:str, log=lambda m:None)->ProductRecord|None:
    pipe=ProductPipeline()
    candidates=[]
    if item.source_url:
        candidates=[type('C',(),{'url':item.source_url,'likely_official':True,'score':1.0})()]
    else:
        candidates=search_web(item.identity,limit=10)
    errors=[]
    for cand in candidates:
        try:
            host=(urlparse(cand.url).hostname or '').removeprefix('www.')
            official_domain=host if getattr(cand,'likely_official',False) else None
            log(f"  probando: {cand.url}")
            rec=pipe.process_url(item.identity,cand.url,official_domain=official_domain,include_pdfs=True,include_images=True,browser_fallback=True)
            # Secondary candidates must already be EXACT by pipeline policy. For official candidates HIGH is allowed,
            # but a contradictory strong identifier is never accepted.
            if rec.identity.identifiers_conflicting: raise ValueError('identificadores en conflicto')
            Path(out_dir).mkdir(parents=True,exist_ok=True)
            stem=re.sub(r'[^A-Za-z0-9._-]+','_',item.identity.mpn or item.identity.ean or item.identity.model or f'row_{item.row}')
            path=Path(out_dir)/f"{stem}.json"
            path.write_text(rec.model_dump_json(indent=2),encoding='utf-8')
            return rec
        except Exception as e:
            errors.append(f"{cand.url}: {type(e).__name__}: {e}")
            continue
    log("  SIN FUENTE VALIDADA: " + (errors[-1] if errors else 'no hubo candidatos'))
    return None


def run_batch(template:str, output_dir:str, overwrite:bool=False, log=lambda m:None, ai_config:AIConfig|None=None, manual_part_numbers:list[str]|None=None)->dict:
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    manual_mode=bool(manual_part_numbers)
    items=manual_items(template,manual_part_numbers or []) if manual_mode else detect_items(template)
    log(f"Productos a procesar: {len(items)}" + (" (part numbers ingresados manualmente)" if manual_mode else " (detectados en Excel)"))
    records=[]
    row_assignments={}
    failures=[]
    for idx,item in enumerate(items,1):
        label=item.identity.mpn or item.identity.ean or item.identity.model or item.identity.product_name
        log(f"[{idx}/{len(items)}] {label}")
        rec=scrape_item(item,str(out/'json'),log=log)
        if rec:
            records.append(rec)
            if manual_mode: row_assignments[(item.sheet,item.row)]=rec
        else:
            failures.append({"part_number":label,"sheet":item.sheet,"row":item.row})
    output_xlsx=str(out/(Path(template).stem+"_completado.xlsx"))
    trace=str(out/'trazabilidad.json')
    report=fill_excel_v8(template,output_xlsx,records,overwrite=overwrite,trace_path=trace,ai_config=ai_config,row_assignments=row_assignments)
    summary={"mode":"manual_part_numbers" if manual_mode else "excel_detected","products_detected":len(items),"products_scraped":len(records),"products_failed":len(failures),"failures":failures,"output_excel":output_xlsx,"trace":trace,"mapping":report.get('summary',{})}
    (out/'resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


# MULTI_SOURCE_PRODUCT_MERGE_V1
def _merge_valid_records(records:list[ProductRecord])->ProductRecord:
    if not records:raise ValueError('no records to merge')
    def rank(rec):return (2 if (rec.fetch or {}).get('source_class')=='manufacturer' else 1,2 if rec.identity.match_level=='EXACT' else 1,float(rec.identity.confidence or 0),len(rec.evidence))
    ordered=sorted(records,key=rank,reverse=True);primary=ordered[0]
    evidence=[];sources=[];warnings=[];notes=[];media_by_url={}
    for rec in ordered:
        evidence.extend(rec.evidence);sources.extend(rec.sources);warnings.extend(rec.warnings);notes.extend(rec.technical_notes)
        for item in rec.media:
            url=item.get('url')
            if not url:continue
            old=media_by_url.get(url)
            if old is None or item.get('confidence',0)>old.get('confidence',0):media_by_url[url]=item
    merged=build_record_strict(primary.identity,evidence,list(dict.fromkeys(sources)))
    merged.media=list(media_by_url.values())
    merged.images=[m for m in merged.media if m.get('media_type')=='image' and m.get('scope') in {'EXACT_VARIANT','EXACT_PRODUCT'} and m.get('confidence',0)>=.80 and m.get('autofill_eligible')]
    merged.videos=[m for m in merged.media if m.get('media_type')=='video' and m.get('scope') in {'EXACT_VARIANT','EXACT_PRODUCT'} and m.get('confidence',0)>=.80 and m.get('autofill_eligible')]
    merged.warnings=list(dict.fromkeys(warnings));merged.technical_notes=notes;merged.site_profile=primary.site_profile
    merged.fetch={'method':'multi_source','source_class':(primary.fetch or {}).get('source_class'),'validated_sources':len(ordered),'manufacturer_sources':sum(1 for r in ordered if (r.fetch or {}).get('source_class')=='manufacturer')}
    return merged

def scrape_item(item:BatchItem, out_dir:str, log=lambda m:None)->ProductRecord|None:
    pipe=ProductPipeline();candidates=[type('C',(),{'url':item.source_url,'likely_official':True,'score':1.0})()] if item.source_url else search_web(item.identity,limit=12)
    errors=[];accepted=[]
    for cand in candidates:
        try:
            host=(urlparse(cand.url).hostname or '').removeprefix('www.');official_domain=host if getattr(cand,'likely_official',False) else None
            log(f'  probando: {cand.url}')
            rec=pipe.process_url(item.identity,cand.url,official_domain=official_domain,include_pdfs=True,include_images=True,browser_fallback=True)
            if rec.identity.identifiers_conflicting:raise ValueError('identificadores en conflicto')
            accepted.append(rec);log(f"  fuente validada: {(rec.fetch or {}).get('source_class','?')} / {rec.identity.match_level}")
            has_manufacturer=any((r.fetch or {}).get('source_class')=='manufacturer' for r in accepted)
            if len(accepted)>=3 or (has_manufacturer and len(accepted)>=2):break
        except Exception as e:errors.append(f'{cand.url}: {type(e).__name__}: {e}')
    if not accepted:
        log('  SIN FUENTE VALIDADA: '+(errors[-1] if errors else 'no hubo candidatos'));return None
    rec=_merge_valid_records(accepted);Path(out_dir).mkdir(parents=True,exist_ok=True)
    stem=re.sub(r'[^A-Za-z0-9._-]+','_',item.identity.mpn or item.identity.ean or item.identity.model or f'row_{item.row}')
    (Path(out_dir)/f'{stem}.json').write_text(rec.model_dump_json(indent=2),encoding='utf-8');return rec


# MULTI_SOURCE_CONSISTENCY_V2
def _meaningful_product_tokens(value:str|None)->set[str]:
    stop={'the','and','with','for','of','de','del','con','para','headphone','headphones','headset','auricular','auriculares','wireless','wired','black','blue','white','negro','azul','blanco','on','ear','in'}
    return {x for x in re.split(r'[^a-z0-9]+',key_norm(value or '')) if len(x)>=2 and x not in stop}

def _cross_source_consistent(primary:ProductRecord, other:ProductRecord, url:str)->bool:
    mpn=str(primary.identity.mpn or '').strip()
    compact_url=re.sub(r'[^a-z0-9]','',key_norm(url or ''))
    compact_mpn=re.sub(r'[^a-z0-9]','',key_norm(mpn))
    if compact_mpn and compact_mpn in compact_url:
        return True
    a=_meaningful_product_tokens(primary.identity.product_name or primary.identity.model)
    b=_meaningful_product_tokens(other.identity.product_name or other.identity.model)
    if not a or not b:
        return False
    shared=a & b
    return len(shared)>=max(2,min(3,len(a)//2))

def scrape_item(item:BatchItem, out_dir:str, log=lambda m:None)->ProductRecord|None:
    pipe=ProductPipeline();candidates=[type('C',(),{'url':item.source_url,'likely_official':True,'score':1.0})()] if item.source_url else search_web(item.identity,limit=12)
    errors=[];accepted=[]
    for cand in candidates:
        try:
            host=(urlparse(cand.url).hostname or '').removeprefix('www.')
            official_domain=host if getattr(cand,'likely_official',False) else None
            # In manual-MPN mode the brand is initially unknown. Once the first exact
            # page identifies the brand, use it to recognize later manufacturer hosts.
            if not official_domain and accepted:
                brand=re.sub(r'[^a-z0-9]','',key_norm(accepted[0].identity.brand or ''))
                hcompact=re.sub(r'[^a-z0-9]','',key_norm(host))
                if brand and brand in hcompact:
                    official_domain=host
            log(f'  probando: {cand.url}')
            rec=pipe.process_url(item.identity,cand.url,official_domain=official_domain,include_pdfs=True,include_images=True,browser_fallback=True)
            if rec.identity.identifiers_conflicting:raise ValueError('identificadores en conflicto')
            if accepted and not _cross_source_consistent(accepted[0],rec,cand.url):
                raise ValueError('fuente exacta contiene el MPN pero no representa la misma ficha de producto')
            accepted.append(rec);log(f"  fuente validada: {(rec.fetch or {}).get('source_class','?')} / {rec.identity.match_level}")
            has_manufacturer=any((r.fetch or {}).get('source_class')=='manufacturer' for r in accepted)
            if len(accepted)>=3 or (has_manufacturer and len(accepted)>=2):break
        except Exception as e:errors.append(f'{cand.url}: {type(e).__name__}: {e}')
    if not accepted:
        log('  SIN FUENTE VALIDADA: '+(errors[-1] if errors else 'no hubo candidatos'));return None
    rec=_merge_valid_records(accepted);Path(out_dir).mkdir(parents=True,exist_ok=True)
    stem=re.sub(r'[^A-Za-z0-9._-]+','_',item.identity.mpn or item.identity.ean or item.identity.model or f'row_{item.row}')
    (Path(out_dir)/f'{stem}.json').write_text(rec.model_dump_json(indent=2),encoding='utf-8');return rec
