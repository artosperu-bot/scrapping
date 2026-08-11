from pathlib import Path
from textwrap import dedent


def patch_field_derivations():
    p = Path('src/product_intelligence/field_derivations.py')
    s = p.read_text(encoding='utf-8')
    marker = '# TEMPLATE_DESCRIPTION_SMARTNESS_V1'
    if marker in s:
        return
    s += dedent(r'''

    # TEMPLATE_DESCRIPTION_SMARTNESS_V1
    def _smart_translate_label(label: str) -> str:
        n=key_norm(label)
        rules=[
            (r'driver size|driver \(mm\)','Tamaño del driver'),
            (r'driver type','Tipo de driver'),
            (r'frequency response|dynamic frequency','Respuesta de frecuencia'),
            (r'impedance','Impedancia'),
            (r'sensitivity','Sensibilidad'),
            (r'battery life|play time|music play|maximum play','Autonomía'),
            (r'charging time|quick charging|charge time','Tiempo de carga'),
            (r'battery chemistry','Tipo de batería'),
            (r'bluetooth version','Versión Bluetooth'),
            (r'bluetooth profiles','Perfiles Bluetooth'),
            (r'connectivity technology|^connectivity$|^connection$','Conectividad'),
            (r'^wireless$','Conexión inalámbrica'),
            (r'audio connector|wired audio connector','Conector de audio'),
            (r'microphone','Micrófono'),
            (r'weight','Peso'),
            (r'water resistance|water resistant|ip code|ip rating','Resistencia al agua'),
            (r'power supply|power source','Alimentación'),
            (r'dimensions','Dimensiones')]
        for pat,es in rules:
            if re.search(pat,n,re.I): return es
        return label

    def _smart_translate_value(value: str) -> str:
        v=str(value)
        for pat,rep in [(r'\bYes\b','Sí'),(r'\bWireless\b','Inalámbrico'),(r'\bWired\b','Cableado'),
                        (r'\bBlack\b','Negro'),(r'\bBlue\b','Azul'),(r'\bWhite\b','Blanco'),
                        (r'\bHours?\b','h'),(r'\bMinutes?\b','min'),
                        (r'No Wired Audio Support','Sin soporte de audio por cable')]:
            v=re.sub(pat,rep,v,flags=re.I)
        return v

    def _smart_looks_english(text: str) -> bool:
        n=key_norm(text)
        en=sum(1 for w in ['the','with','and','for','wireless','wired','headphones','headset','battery','sound'] if re.search(rf'\b{re.escape(w)}\b',n))
        es=sum(1 for w in ['con','para','auriculares','bateria','sonido','inalambrico','cableado'] if re.search(rf'\b{re.escape(w)}\b',n))
        return en>es and en>=2

    def derive_description(rec: ProductRecord) -> Derived:
        rows=_find_evidence(rec,[r'^description$',r'descripcion',r'descripci[oó]n'])
        base=None;base_ev=None;base_q=0.0
        for q,ev,v in rows:
            clean=re.sub(r'<[^>]+>',' ',v);clean=re.sub(r'\s+',' ',clean).strip()
            if 8<=len(clean)<=2500:base=clean;base_ev=ev;base_q=q;break
        tech=re.compile(r'driver|frequency|frecuencia|impedance|impedancia|sensitivity|sensibilidad|battery|bater[ií]a|charging|carga|play time|autonom|weight|peso|dimension|interface|interfaz|connect|conect|bluetooth|wifi|usb|hdmi|water|agua|ip rating|ip code|microphone|micr[oó]fono|audio|power supply|alimentaci[oó]n',re.I)
        deny=re.compile(r'support|subscription|newsletter|price|precio|review|rese[ñn]a|legal|declaration',re.I)
        facts=[];seen=set()
        for ev,q in iter_clean_evidence(rec):
            if len(facts)>=12:break
            a=str(ev.attribute or '').strip()
            if not a or deny.search(a) or not tech.search(a):continue
            v=ev.normalized_value if ev.normalized_value not in (None,'') else ev.raw_value
            sv=re.sub(r'<[^>]+>',' ',str(v or ''));sv=re.sub(r'\s+',' ',sv).strip()
            if not sv or len(sv)>180 or deny.search(sv):continue
            k=key_norm(a+' '+sv)
            if k in seen:continue
            seen.add(k);facts.append((_smart_translate_label(a),_smart_translate_value(sv),q,ev))
        name=_smart_translate_value(str(rec.identity.product_name or rec.identity.model or rec.identity.brand or 'Producto'))
        suffix='; '.join(f'{a}: {v}' for a,v,_,_ in facts[:8])
        if base and not _smart_looks_english(base):
            if len(base)>=420 or not suffix:return Derived(base,min(.99,base_q+.05),'official_description_es',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
            return Derived((base.rstrip('. ')+'. Especificaciones verificadas: '+suffix+'.')[:2400],min(.98,base_q+.04),'official_description_es_plus_verified_specs',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
        if suffix:return Derived(f'{name}. Especificaciones verificadas: {suffix}.',.91,'spanish_verified_specs_description',base_ev.source_url if base_ev else None,base_ev.attribute if base_ev else None,base_ev.raw_value if base_ev else None)
        if base:return Derived(base,min(.90,base_q),'verified_description_untranslated_fallback',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
        return Derived(reason='description_not_found')

    def derive_boolean(rec: ProductRecord, concept: str) -> Derived:
        pats={'bluetooth':[r'bluetooth',r'perfiles bluetooth',r'versi[oó]n bluetooth'],
              'water_resistance':[r'water resistance',r'water resistant',r'resistente al agua',r'ip\s*[0-9x]{2}'],
              'serial_number':[r'serial number',r'n[uú]mero de serie']}.get(concept,[])
        if not pats:return Derived(reason='unknown_boolean')
        rows=_find_evidence(rec,pats)
        for q,ev,v in rows:
            n=key_norm(v)
            if n in {'si','yes','true','1','supported','included'} or n.startswith('yes '):return Derived('Sí',min(.99,q+.04),'explicit_yes',ev.source_url,ev.attribute,ev.raw_value)
            if n in {'no','false','0','none','not supported','unsupported'} or n.startswith('no '):return Derived('No',min(.99,q+.04),'explicit_no',ev.source_url,ev.attribute,ev.raw_value)
            if concept=='bluetooth' and 'bluetooth' in key_norm(ev.attribute) and str(v).strip():return Derived('Sí',min(.98,q+.03),'bluetooth_specific_evidence',ev.source_url,ev.attribute,ev.raw_value)
            if concept=='water_resistance' and re.search(r'\bIP\s*(?:[0-9]{2}|X[0-9])\b',v,re.I):return Derived('Sí',min(.98,q+.03),'ip_rating_presence',ev.source_url,ev.attribute,ev.raw_value)
        if concept=='bluetooth':
            conn=_find_evidence(rec,[r'^connectivity$',r'^connection$',r'^wireless$',r'audio connector',r'wired audio connector',r'interface'])
            joined=' '.join(f'{ev.attribute} {v}' for _,ev,v in conn);n=key_norm(joined)
            if conn and re.search(r'wired audio connector|audio connector|connectivity',n,re.I) and ('usb c' in n or '3 5mm' in n or '3.5mm' in joined.lower()) and not re.search(r'wireless|2 4 ghz|radio rf|bluetooth',n,re.I):
                q,ev,v=conn[0];return Derived('No',min(.94,max(.88,q+.04)),'closed_connectivity_wired_only',ev.source_url,ev.attribute,ev.raw_value)
            if conn and re.search(r'2[ .]?4\s*ghz|radio\s*/?\s*rf',joined,re.I) and 'bluetooth' not in n:
                q,ev,v=conn[0];return Derived('No',min(.93,max(.87,q+.03)),'closed_connectivity_2_4ghz_rf_only',ev.source_url,ev.attribute,ev.raw_value)
        return Derived(reason='boolean_not_proven')
    ''')
    p.write_text(s,encoding='utf-8')


def patch_batch():
    p=Path('src/product_intelligence/batch.py')
    s=p.read_text(encoding='utf-8')
    marker='# MULTI_SOURCE_PRODUCT_MERGE_V1'
    if marker in s:
        return
    s=s.replace('from .pipeline import ProductPipeline\n','from .pipeline import ProductPipeline\nfrom .record_builder import build_record_strict\n')
    s += dedent(r'''

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
    ''')
    p.write_text(s,encoding='utf-8')


def write_tests():
    Path('tests/test_template_description_guidance.py').write_text(dedent(r'''
    from product_intelligence.models import ProductIdentity, ProductRecord, Evidence
    from product_intelligence.field_derivations import derive_boolean, derive_description
    from product_intelligence.semantic_guard import infer_contract
    def rec(*ev):return ProductRecord(identity=ProductIdentity(mpn='TEST',match_level='EXACT'),evidence=list(ev))
    def e(a,v):return Evidence(attribute=a,raw_value=v,normalized_value=v,source_url='https://example.test/p',source_type='manufacturer_html',match_level='EXACT',confidence=.95)
    def test_description_can_define_boolean_contract():
        c=infer_contract('OpaqueField','Selecciona si el producto cuenta con bluetooth. // Select whether the product has Bluetooth. - Syntax: One value from the list',None,'UNKNOWN');assert c.semantic=='bluetooth' and c.value_type=='controlled'
    def test_bluetooth_yes_from_specific_technology_evidence():assert derive_boolean(rec(e('Bluetooth Version','5.4')),'bluetooth').value=='Sí'
    def test_bluetooth_no_from_closed_wired_connectivity():assert derive_boolean(rec(e('Connectivity','1x USB-C'),e('Wired Audio Connector','1x USB-C')),'bluetooth').value=='No'
    def test_bluetooth_no_from_closed_24ghz_rf_connectivity():assert derive_boolean(rec(e('Connectivity','2.4 GHz Radio/RF')),'bluetooth').value=='No'
    def test_spanish_description_uses_translated_fact_labels():
        r=rec(e('description','Enjoy wireless listening with powerful sound.'),e('Frequency Response','20 Hz to 20 kHz'),e('Impedance','32 Ohms'));r.identity.product_name='Test Headphones';d=derive_description(r);assert 'Respuesta de frecuencia' in d.value and 'Impedancia' in d.value
    '''),encoding='utf-8')


if __name__=='__main__':
    patch_field_derivations()
    patch_batch()
    write_tests()
