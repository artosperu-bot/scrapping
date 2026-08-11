from pathlib import Path
from textwrap import dedent

p=Path('src/product_intelligence/field_derivations.py')
s=p.read_text(encoding='utf-8')
marker='# BLUETOOTH_AND_SPANISH_FINAL_V2'
if marker not in s:
    s += dedent(r'''

    # BLUETOOTH_AND_SPANISH_FINAL_V2
    def _smart_translate_value(value: str) -> str:
        v=str(value)
        replacements=[
            (r'Not Specified by Manufacturer','No especificado por el fabricante'),
            (r'No Wired Audio Support','Sin soporte de audio por cable'),
            (r'\bWireless Gaming Headset\b','auricular gamer inalámbrico'),
            (r'\bGaming Headset\b','auricular gamer'),
            (r'\bOn-Ear USB-C Headphones\b','auriculares on-ear USB-C'),
            (r'\bOn-Ear Headphones\b','auriculares on-ear'),
            (r'\bWireless Headphones?\b','auriculares inalámbricos'),
            (r'\bWireless Headset\b','auricular inalámbrico'),
            (r'\bHeadphones?\b','auriculares'),
            (r'\bWireless\b','Inalámbrico'),
            (r'\bWired\b','Cableado'),
            (r'\bDynamic\b','Dinámico'),
            (r'\bBlack\b','Negro'),(r'\bBlue\b','Azul'),(r'\bWhite\b','Blanco'),
            (r'\bHours?\b','h'),(r'\bMinutes?\b','min'),
            (r'(?<=\d)\s+to\s+(?=\d)',' a '),
            (r'\bYes\b','Sí')]
        for pat,rep in replacements:
            v=re.sub(pat,rep,v,flags=re.I)
        return v

    def derive_boolean(rec: ProductRecord, concept: str) -> Derived:
        pats={'bluetooth':[r'bluetooth',r'perfiles bluetooth',r'versi[oó]n bluetooth'],
              'water_resistance':[r'water resistance',r'water resistant',r'resistente al agua',r'ip\s*[0-9x]{2}'],
              'serial_number':[r'serial number',r'n[uú]mero de serie']}.get(concept,[])
        if not pats:return Derived(reason='unknown_boolean')
        rows=_find_evidence(rec,pats)
        for q,ev,v in rows:
            n=key_norm(v)
            if n in {'si','yes','true','1','supported','included'} or n.startswith('yes '):return Derived('Sí',max(.90,min(.99,q+.08)),'explicit_yes',ev.source_url,ev.attribute,ev.raw_value)
            if n in {'no','false','0','none','not supported','unsupported'} or n.startswith('no '):return Derived('No',max(.90,min(.99,q+.08)),'explicit_no',ev.source_url,ev.attribute,ev.raw_value)
            if concept=='bluetooth' and 'bluetooth' in key_norm(ev.attribute) and str(v).strip():return Derived('Sí',max(.90,min(.98,q+.14)),'bluetooth_specific_evidence',ev.source_url,ev.attribute,ev.raw_value)
            if concept=='water_resistance' and re.search(r'\bIP\s*(?:[0-9]{2}|X[0-9])\b',v,re.I):return Derived('Sí',max(.90,min(.98,q+.08)),'ip_rating_presence',ev.source_url,ev.attribute,ev.raw_value)
        if concept=='bluetooth':
            for ev,q in iter_clean_evidence(rec):
                a=key_norm(str(ev.attribute or '')); v=str(ev.normalized_value if ev.normalized_value not in (None,'') else ev.raw_value or '')
                nv=key_norm(v)
                if any(x in a for x in ['connectivity','conectividad','connection','wireless technology']) and 'bluetooth' in nv:
                    return Derived('Sí',max(.88,min(.97,q+.08)),'connectivity_explicit_bluetooth',ev.source_url,ev.attribute,ev.raw_value)
            conn=_find_evidence(rec,[r'^connectivity$',r'^conectividad$',r'^connection$',r'^wireless$',r'audio connector',r'wired audio connector',r'interface'])
            joined=' '.join(f'{ev.attribute} {v}' for _,ev,v in conn);n=key_norm(joined)
            if conn and re.search(r'wired audio connector|audio connector|connectivity|conectividad',n,re.I) and ('usb c' in n or '3 5mm' in n or '3.5mm' in joined.lower()) and not re.search(r'wireless|2 4 ghz|radio rf|bluetooth',n,re.I):
                q,ev,v=conn[0];return Derived('No',min(.94,max(.88,q+.04)),'closed_connectivity_wired_only',ev.source_url,ev.attribute,ev.raw_value)
            if conn and re.search(r'2[ .]?4\s*ghz|radio\s*/?\s*rf',joined,re.I) and 'bluetooth' not in n:
                q,ev,v=conn[0];return Derived('No',min(.93,max(.87,q+.03)),'closed_connectivity_2_4ghz_rf_only',ev.source_url,ev.attribute,ev.raw_value)
        return Derived(reason='boolean_not_proven')

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
            if suffix:return Derived((base.rstrip('. ')+'. Especificaciones verificadas: '+suffix+'.')[:2400],min(.98,max(.91,base_q+.04)),'spanish_description_plus_verified_specs',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
            return Derived(base,min(.95,max(.88,base_q)),'spanish_description',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
        if base:
            base_es=_smart_translate_value(base)
            if suffix:return Derived((base_es.rstrip('. ')+'. Especificaciones verificadas: '+suffix+'.')[:2400],.91,'translated_source_plus_verified_specs',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
            return Derived(base_es,min(.90,base_q),'translated_description_fallback',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
        if suffix:return Derived(f'{name}. Especificaciones verificadas: {suffix}.',.91,'spanish_verified_specs_description')
        return Derived(reason='description_not_found')
    ''')
    p.write_text(s,encoding='utf-8')
