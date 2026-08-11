from pathlib import Path
from textwrap import dedent

p=Path('src/product_intelligence/batch.py')
s=p.read_text(encoding='utf-8')
marker='# MULTI_SOURCE_CONSISTENCY_V2'
if marker not in s:
    s += dedent(r'''

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
    ''')
    p.write_text(s,encoding='utf-8')
