from pathlib import Path

p=Path('src/product_intelligence/excel_mapper_v8.py')
s=p.read_text(encoding='utf-8')
if 'description,canonical,contract' not in s:
    s=s.replace('def _derived_for_field(rec,header,canonical,contract,options,ext_id):','def _derived_for_field(rec,header,description,canonical,contract,options,ext_id):')
    s=s.replace('    n=key_norm(_strip_field_id(header))\n    # Existing V5 safe derivations.', '    n=key_norm(_strip_field_id(header))\n    intent=key_norm(f"{header} {description or \'\'} {getattr(contract, \'semantic\', None) or \'\'}")\n    # Existing V5 safe derivations.')
    s=s.replace("ext_id=='1568' or 'bluetooth' in n", "ext_id=='1568' or 'bluetooth' in intent")
    s=s.replace("ext_id=='36083' or 'resistentealagua' in n or 'waterresistance' in n", "ext_id=='36083' or any(x in intent for x in ['resistentealagua','resistente al agua','waterresistance','water resistance'])")
    s=s.replace("ext_id=='1651' or 'conectividad' in n or 'connectivity' in n", "ext_id=='1651' or 'conectividad' in intent or 'connectivity' in intent")
    s=s.replace("ext_id=='1661' or 'tipodeauricular' in n", "ext_id=='1661' or 'tipodeauricular' in intent or 'tipo de auricular' in intent or 'type of headphones' in intent")
    s=s.replace("ext_id=='1672' or 'autonomia' in n", "ext_id=='1672' or 'autonomia' in intent or 'battery life' in intent")
    s=s.replace("_derived_for_field(rec,header,key,contracts[c],options,ext)", "_derived_for_field(rec,header,str(desc) if desc else None,key,contracts[c],options,ext)")
    p.write_text(s,encoding='utf-8')
