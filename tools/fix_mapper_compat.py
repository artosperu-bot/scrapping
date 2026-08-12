from pathlib import Path

p=Path(__file__).resolve().parents[1]/'src/product_intelligence/excel_mapper_v8.py'
s=p.read_text(encoding='utf-8')
s=s.replace('derive_power_source,derive_battery_life,derive_features,derive_segment,derive_bluetooth','derive_power_source,derive_autonomy,derive_features,derive_segment,derive_boolean')
s=s.replace("elif 'bluetooth' in intent:d=derive_bluetooth(rec,options)","elif 'bluetooth' in intent:d=derive_boolean(rec,'bluetooth')")
s=s.replace("elif canonical=='battery life' or 'autonomia' in intent or 'battery life' in intent:d=derive_battery_life(rec)","elif canonical=='battery life' or 'autonomia' in intent or 'battery life' in intent:d=derive_autonomy(rec)")
s=s.replace('if d.raw_value is not None:ev_raw=d.raw_value','if d.evidence_raw is not None:ev_raw=d.evidence_raw')
s=s.replace("conf=float(rec.identity.confidence or 0)\n    return val,conf,'identity'","conf=.99 if rec.identity.match_level=='EXACT' else (.90 if rec.identity.match_level=='HIGH' else float(rec.identity.confidence or 0))\n    return val,conf,'identity'")
p.write_text(s,encoding='utf-8')
print('mapper compatibility fixed')
