from pathlib import Path
p=Path('src/product_intelligence/field_derivations.py')
s=p.read_text(encoding='utf-8')
old='''    if base:
        base_es=_smart_translate_value(base)
        if suffix:return Derived((base_es.rstrip('. ')+'. Especificaciones verificadas: '+suffix+'.')[:2400],.91,'translated_source_plus_verified_specs',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
        return Derived(base_es,min(.90,base_q),'translated_description_fallback',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
    if suffix:return Derived(f'{name}. Especificaciones verificadas: {suffix}.',.91,'spanish_verified_specs_description')
'''
new='''    if base:
        # Short technical descriptions can be translated with the controlled phrase dictionary.
        # Long marketing prose is never translated word-by-word because that produces Spanglish;
        # for that case use identity plus verified technical facts only.
        if len(base) <= 120:
            short_es=_translate_base_description(base)
            if suffix:
                return Derived((short_es.rstrip('. ')+'. Especificaciones verificadas: '+suffix+'.')[:2400],.92,'controlled_short_translation_plus_verified_facts',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
            return Derived(short_es,min(.90,base_q),'controlled_short_translation',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
        if suffix:
            return Derived(f'{name}. Especificaciones verificadas: {suffix}.'[:2400],.92,'controlled_spanish_from_verified_facts',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
        return Derived(name,.84,'spanish_identity_only_when_source_language_untranslated',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
    if suffix:return Derived(f'{name}. Especificaciones verificadas: {suffix}.',.91,'spanish_verified_specs_description')
'''
if old not in s: raise SystemExit('description anchor missing')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('patched description')
