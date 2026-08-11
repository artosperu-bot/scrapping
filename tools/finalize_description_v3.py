from pathlib import Path
from textwrap import dedent

p=Path('src/product_intelligence/field_derivations.py')
s=p.read_text(encoding='utf-8')
marker='# DESCRIPTION_LONG_ENGLISH_V3'
if marker not in s:
    s += dedent(r'''

    # DESCRIPTION_LONG_ENGLISH_V3
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
            if suffix:return Derived((base.rstrip('. ')+'. Especificaciones verificadas: '+suffix+'.')[:2400],.91,'spanish_description_plus_verified_specs',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
            return Derived(base,.90,'spanish_description',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
        if base and _smart_looks_english(base):
            # Short factual phrases can be translated deterministically. Long marketing
            # paragraphs should not be translated word by word; build clean Spanish copy
            # from product identity plus verified technical facts instead.
            prefix=_smart_translate_value(base) if len(base)<=120 else name
            if suffix:return Derived((prefix.rstrip('. ')+'. Especificaciones verificadas: '+suffix+'.')[:2400],.91,'clean_spanish_from_verified_evidence',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
            return Derived(prefix,.88,'translated_short_description',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
        if suffix:return Derived(f'{name}. Especificaciones verificadas: {suffix}.',.91,'spanish_verified_specs_description')
        return Derived(reason='description_not_found')
    ''')
    p.write_text(s,encoding='utf-8')
