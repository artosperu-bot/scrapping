from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .attribute_resolver import iter_clean_evidence
from .models import ProductRecord
from .normalize import key_norm


@dataclass
class Derived:
    value: Any = None
    confidence: float = 0.0
    reason: str = ""
    source: str | None = None
    evidence_attribute: str | None = None
    evidence_raw: Any = None


def _all_text(rec: ProductRecord) -> str:
    parts=[]
    i=rec.identity
    for v in [i.product_name,i.model,i.brand,i.color,i.capacity,i.variant]:
        if v: parts.append(str(v))
    for ev,_ in iter_clean_evidence(rec):
        if ev.attribute: parts.append(str(ev.attribute))
        if ev.raw_value not in (None,""): parts.append(str(ev.raw_value))
    return " \n ".join(parts)


def _find_evidence(rec: ProductRecord, attr_patterns: list[str], value_pattern: str | None = None):
    rows=[]
    for ev,q in iter_clean_evidence(rec):
        a=key_norm(ev.attribute)
        v=str(ev.normalized_value if ev.normalized_value not in (None,"") else ev.raw_value)
        if not any(re.search(p,a,re.I) for p in attr_patterns):
            continue
        if value_pattern and not re.search(value_pattern,v,re.I):
            continue
        rows.append((max(q,float(ev.confidence or 0)),ev,v))
    rows.sort(key=lambda x:x[0],reverse=True)
    return rows


def derive_description(rec: ProductRecord) -> Derived:
    """Build a fuller evidence-grounded description without category-specific rules.

    The official description remains the base. When it is short, append a compact set of
    high-quality technical facts. This mirrors the human workflow used during regression
    tests while remaining deterministic and auditable.
    """
    rows=_find_evidence(rec,[r"^description$",r"descripcion",r"descripci[oó]n"])
    base=None; base_ev=None; base_q=0.0
    for q,ev,v in rows:
        if 8 <= len(v) <= 2500:
            base=v.strip();base_ev=ev;base_q=q;break

    technical_pat=re.compile(
        r"driver|frequency|frecuencia|impedance|impedancia|sensitivity|sensibilidad|"
        r"battery|bater[ií]a|charging|carga|play time|autonom|weight|peso|dimension|"
        r"interface|interfaz|connect|conect|bluetooth|wifi|usb|hdmi|processor|procesador|"
        r"memory|memoria|storage|almacenamiento|capacity|capacidad|resolution|resoluci[oó]n|"
        r"water|agua|ip rating|certificaci[oó]n ip|mtbf|warranty|garant[ií]a|nand|tbw|"
        r"microphone|micr[oó]fono|screen|pantalla|refresh|audio|power supply|alimentaci[oó]n",re.I)
    deny=re.compile(r"support|why buy|subscription|newsletter|price|precio|review|rese[ñn]a|"
                    r"legal|declaration|article|signed|software update period",re.I)
    facts=[];seen=set()
    for ev,q in iter_clean_evidence(rec):
        if len(facts)>=10:break
        a=str(ev.attribute or '').strip()
        if not a or deny.search(a) or not technical_pat.search(a):continue
        v=ev.normalized_value if ev.normalized_value not in (None,'') else ev.raw_value
        if v in (None,''):continue
        sv=str(v).strip()
        if not sv or len(sv)>180 or deny.search(sv):continue
        k=key_norm(a+" "+sv)
        if k in seen:continue
        seen.add(k);facts.append((a,sv,q,ev))

    if base:
        if len(base)>=420 or not facts:
            return Derived(base,min(.99,base_q+.05),"official_description",base_ev.source_url,base_ev.attribute,base_ev.raw_value)
        suffix='; '.join(f"{a}: {v}" for a,v,_,_ in facts[:7])
        text=base.rstrip('. ') + ". Especificaciones verificadas: " + suffix + "."
        return Derived(text[:2400],min(.98,base_q+.04),"official_description_plus_verified_specs",base_ev.source_url,base_ev.attribute,base_ev.raw_value)
    if facts:
        name=rec.identity.product_name or rec.identity.model or rec.identity.brand or "Producto"
        suffix='; '.join(f"{a}: {v}" for a,v,_,_ in facts[:9])
        return Derived(f"{name}. Especificaciones verificadas: {suffix}.",.90,"verified_specs_description")
    return Derived(reason="description_not_found")


def derive_boolean(rec: ProductRecord, concept: str) -> Derived:
    pats={
        "bluetooth":[r"bluetooth",r"perfiles bluetooth",r"versi[oó]n bluetooth"],
        "water_resistance":[r"water resistance",r"water resistant",r"resistente al agua",r"ip\d{2}"],
        "serial_number":[r"serial number",r"n[uú]mero de serie"],
    }.get(concept,[])
    if not pats: return Derived(reason="unknown_boolean")
    rows=_find_evidence(rec,pats)
    for q,ev,v in rows:
        n=key_norm(v)
        if n in {"si","yes","true"}:
            return Derived("Sí",min(.99,q+.04),"explicit_yes",ev.source_url,ev.attribute,ev.raw_value)
        if n in {"no","false"} or n.startswith("no "):
            return Derived("No",min(.99,q+.04),"explicit_no",ev.source_url,ev.attribute,ev.raw_value)
        if concept=="bluetooth" and (re.search(r"\d",v) or "profile" in key_norm(ev.attribute) or "perfil" in key_norm(ev.attribute)):
            return Derived("Sí",min(.98,q+.03),"technology_presence",ev.source_url,ev.attribute,ev.raw_value)
        if concept=="water_resistance" and re.search(r"\bIP\s*\d{2}\b",v,re.I):
            return Derived("Sí",min(.98,q+.03),"ip_rating_presence",ev.source_url,ev.attribute,ev.raw_value)
    return Derived(reason="boolean_not_proven")


def derive_autonomy(rec: ProductRecord) -> Derived:
    rows=_find_evidence(rec,[r"battery life",r"play time",r"music play",r"tiempo de juego",r"reproducci[oó]n",r"autonom",r"duraci[oó]n de bater"],r"\d")
    best=None
    for q,ev,v in rows:
        m=re.search(r"(\d+(?:[.,]\d+)?)\s*(h|hr|hrs|hours?|horas?)\b",v,re.I)
        if m:
            hours=float(m.group(1).replace(",","."))
        elif re.search(r"hour|hours|hora|horas", key_norm(ev.attribute), re.I) and re.fullmatch(r"\s*\d+(?:[.,]\d+)?\s*",v):
            hours=float(v.strip().replace(",","."))
        else:
            continue
        score=q
        if re.search(r"max|maximum|m[aá]ximo|play|music|reprodu",key_norm(ev.attribute),re.I): score+=.05
        if best is None or score>best[0]: best=(score,ev,hours)
    if best:
        score,ev,h=best
        val=f"{int(h) if h.is_integer() else h:g} h"
        return Derived(val,min(.99,score),"verified_playtime",ev.source_url,ev.attribute,ev.raw_value)
    return Derived(reason="autonomy_not_found")


def derive_connectivity(rec: ProductRecord, options: list[Any]) -> Derived:
    option_map={key_norm(str(o)):str(o) for o in options}
    wanted=[]
    def add_option(keys:list[str]):
        for k in keys:
            nk=key_norm(k)
            if nk in option_map and option_map[nk] not in wanted:
                wanted.append(option_map[nk]); return True
        return False

    relevant=[]
    excluded=[]
    for ev,_q in iter_clean_evidence(rec):
        attr=key_norm(ev.attribute)
        val=str(ev.normalized_value if ev.normalized_value not in (None,"") else ev.raw_value)
        joined=key_norm(f"{ev.attribute} {val}")
        if re.search(r"charg|carga|power input|alimentaci[oó]n|battery|bater[ií]a",attr,re.I):
            excluded.append(joined); continue
        if re.search(r"connect|conect|interface|interfaz|audio connector|audio connection|wired|wireless|bluetooth|usb|hdmi|ethernet|rj 45|thunderbolt|jack",joined,re.I):
            relevant.append(joined)
    identity_text=key_norm(" ".join(x for x in [rec.identity.product_name,rec.identity.model] if x))
    text=key_norm(" ".join([identity_text,*relevant]))

    # USB counts only when proven in an interface/audio/data context, never from charging alone.
    if any(re.search(r"usb c|usbc",x,re.I) for x in relevant): add_option(["USB-C","USB C"])
    elif any(re.search(r"\busb\b",x,re.I) for x in relevant): add_option(["USB"])
    if "bluetooth" in text: add_option(["Bluetooth"])
    if "wifi 6" in text: add_option(["Wifi 6","Wifi"])
    elif "wifi" in text or "wi fi" in text: add_option(["Wifi"])
    if "ethernet" in text or "rj 45" in text: add_option(["Ethernet"])
    if "hdmi" in text: add_option(["HDMI"])
    if "thunderbolt" in text: add_option(["Thunderbolt"])
    if "3 5mm" in text or "3.5mm" in " ".join(relevant).lower(): add_option(["Auxiliar 3.5mm"])
    if re.search(r"wireless|inal[aá]mbric|2 4g wireless|2 4 ghz",text):
        add_option(["Inalámbrico","WF wireless"])
        if re.search(r"2 4g|2 4 ghz|radio ?frequency|radiofrecuencia|rf\b",text,re.I):
            add_option(["Radiofrecuencia (RF)","RF"])
    if re.search(r"\bwired\b|(?<!in)al[aá]mbric|cableado",text): add_option(["Alámbrico","Cableado"])
    if wanted:
        return Derived(", ".join(wanted),.95,"connectivity_from_interface_evidence_excluding_charging")
    has_interface=bool(relevant)
    if has_interface and "otro" in option_map:
        return Derived(option_map["otro"],.88,"real_interface_not_represented_in_marketplace_options")
    return Derived(reason="connectivity_not_proven_or_not_mappable")


def derive_headphone_type(rec: ProductRecord, options: list[Any]) -> Derived:
    text=key_norm(_all_text(rec))
    opts={key_norm(str(o)):str(o) for o in options}
    concepts=[]
    if re.search(r"gaming headset|gaming headphone|gamer",text): concepts += ["Gamer"]
    if re.search(r"over ear|circumaural",text): concepts += ["Auriculares Over-Ear","Over-Ear","Over Ear","Circumaural"]
    if re.search(r"on ear|supraaural",text): concepts += ["Auriculares On-ear","On-Ear","On Ear","Supraaural"]
    if re.search(r"in ear|earbud|intraaural",text): concepts += ["Auriculares In-ear","In-Ear","In Ear","Intraaural"]
    if "headset" in text: concepts += ["Headset"]
    for c in concepts:
        if key_norm(c) in opts:
            return Derived(opts[key_norm(c)],.92,"explicit_form_factor_to_allowed_option")
    return Derived(reason="headphone_type_not_proven")


def derive_package_contents(rec: ProductRecord) -> Derived:
    rows=_find_evidence(rec,[r"package contents",r"what.?s in the box",r"contenido del paquete",r"contenido de la caja"])
    for q,ev,v in rows:
        if 2 <= len(v.split()) <= 80 and not re.search(r"get even more|personalization|control and",v,re.I):
            return Derived(v,min(.98,q+.04),"explicit_package_contents",ev.source_url,ev.attribute,ev.raw_value)
    return Derived(reason="package_contents_not_found")


def derive_controlled_color(rec: ProductRecord, options:list[Any]) -> Derived:
    if not rec.identity.color: return Derived(reason="color_unknown")
    opts={key_norm(str(o)):str(o) for o in options}
    n=key_norm(rec.identity.color)
    if n in opts: return Derived(opts[n],.98,"identity_color_exact_option")
    aliases={"black":"negro","blue":"azul","white":"blanco","red":"rojo","green":"verde","gray":"gris","grey":"gris","beige":"beige"}
    if n in aliases and key_norm(aliases[n]) in opts:
        return Derived(opts[key_norm(aliases[n])],.96,"identity_color_translated_option")
    return Derived(reason="color_not_in_allowed_options")


def derive_water_resistance(rec: ProductRecord, options:list[Any]) -> Derived:
    opts={key_norm(str(o)):str(o) for o in options}
    rows=_find_evidence(rec,[r"ip rating",r"certificacion ip",r"certificaci[oó]n ip",r"water resistance",r"resistente al agua",r"^ip$"])
    rating=None; src=None
    for q,ev,v in rows:
        m=re.search(r"\bIP\s*([0-9]{2}|X[0-9])\b",v,re.I)
        if m:
            rating='IP'+m.group(1).upper();src=(q,ev);break
    if rating:
        nr=key_norm(rating)
        for no,o in opts.items():
            if no==nr or no.startswith(nr+' '):
                q,ev=src
                return Derived(o,min(.99,q+.03),'exact_ip_rating_to_allowed_option',ev.source_url,ev.attribute,ev.raw_value)
        return Derived(reason=f'ip_rating_{rating}_not_in_allowed_options')
    yes=next((o for n,o in opts.items() if n in {'si','yes'}),None)
    if yes:
        b=derive_boolean(rec,'water_resistance')
        if b.value=='Sí': return Derived(yes,b.confidence,b.reason,b.source,b.evidence_attribute,b.evidence_raw)
    return Derived(reason='water_resistance_not_mappable')


def derive_features(rec: ProductRecord, options:list[Any]) -> Derived:
    opts={key_norm(str(o)):str(o) for o in options}
    chosen=[]

    def add_option(names:list[str]):
        for name in names:
            n=key_norm(name)
            if n in opts and opts[n] not in chosen:
                chosen.append(opts[n])
                return True
        return False

    def is_explicit_no(value:Any)->bool:
        n=key_norm(str(value or ""))
        return n in {"no","false","0","none","not supported","unsupported"} or n.startswith("no ")

    def is_explicit_yes(value:Any)->bool:
        n=key_norm(str(value or ""))
        return n in {"si","yes","true","1","supported","included"} or n.startswith("yes ")

    b=derive_boolean(rec,"bluetooth")
    if b.value=="Sí":
        add_option(["Cuenta con Bluetooth"])

    mic_rows=_find_evidence(rec,[r"^microphone$",r"^mic$",r"microphone type",r"micr[oó]fono"])
    for q,ev,v in mic_rows:
        if is_explicit_no(v):
            continue
        if is_explicit_yes(v) or str(v).strip():
            add_option(["Cuenta con micrófono","Cuenta con microfono"])
            break

    anc_rows=_find_evidence(rec,[r"^active noise cancellation$",r"^anc$",r"cancelaci[oó]n de ruido activa"])
    anc_positive=False
    for q,ev,v in anc_rows:
        if is_explicit_no(v):
            continue
        nv=key_norm(v)
        if is_explicit_yes(v) or re.search(r"\benabled\b|\bsupported\b|\bincluded\b",nv,re.I):
            anc_positive=True
            break
    if not anc_positive:
        desc_rows=_find_evidence(rec,[r"^description$",r"descripcion",r"descripci[oó]n"])
        for q,ev,v in desc_rows:
            nv=key_norm(v)
            if re.search(r"active noise cancellation|\banc\b|cancelaci[oó]n de ruido activa",nv,re.I):
                if not re.search(r"\b(no|without|sin|does not|doesn't|not)\b.{0,25}(active noise cancellation|anc|cancelaci)",nv,re.I):
                    anc_positive=True
                    break
    if anc_positive:
        add_option(["Cancelación de ruido activa","Cancelacion de ruido activa"])

    text=key_norm(_all_text(rec))
    generic_signals=[
        (["Carga rápida","Carga rapida"], r"speed charge|fast charge|carga r[aá]pida"),
        (["Entrada de audio auxiliar (3.5mm)","Entrada de audio auxiliar 3 5mm"], r"3[., ]5\s*mm|auxiliary|auxiliar"),
        (["Control por aplicación móvil","Control por aplicacion movil"], r"headphone app|mobile app|aplicaci[oó]n m[oó]vil"),
        (["Cuenta con control de volumen"], r"volume control|control de volumen"),
    ]
    for names,pat in generic_signals:
        if re.search(pat,text,re.I):
            add_option(names)

    if chosen:
        return Derived(", ".join(chosen),.94,"features_from_positive_evidence")
    return Derived(reason="no_allowed_features_proven")


def derive_power_source(rec: ProductRecord, options:list[Any]) -> Derived:
    opts={key_norm(str(o)):str(o) for o in options}
    text=key_norm(_all_text(rec))
    rechargeable=bool(re.search(r'charging time|charge time|tiempo de carga|recharge|recargable',text,re.I))
    battery=bool(re.search(r'battery type|bater[ií]a|lithium ion|li ion',text,re.I))
    usb=bool(re.search(r'power supply[^\n]{0,40}5v|alimentaci[oó]n[^\n]{0,40}usb',text,re.I))
    prefs=[]
    if rechargeable and battery:prefs += ['Batería recargable','Bateria recargable']
    elif battery:prefs += ['Batería','Bateria']
    if usb:prefs += ['USB']
    for p in prefs:
        if key_norm(p) in opts:return Derived(opts[key_norm(p)],.90,'power_source_from_explicit_power_battery_evidence')
    return Derived(reason='power_source_not_mappable')


def derive_segment(rec: ProductRecord, options:list[Any]) -> Derived:
    opts={key_norm(str(o)):str(o) for o in options}; text=key_norm(_all_text(rec))
    if re.search(r'gaming|gamer',text,re.I) and 'gamer' in opts:
        return Derived(opts['gamer'],.94,'explicit_gaming_positioning')
    return Derived(reason='segment_not_proven')

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


# SPANISH_DESCRIPTION_FINAL_V1
def _translate_base_description(text: str) -> str:
    t=re.sub(r'<[^>]+>',' ',str(text or ''));t=re.sub(r'\s+',' ',t).strip()
    replacements=[
        (r'\bwireless headset\b','auricular inalámbrico'),
        (r'\bwireless headphones?\b','auriculares inalámbricos'),
        (r'\bwired headphones?\b','auriculares cableados'),
        (r'\bgaming headset\b','auricular gamer'),
        (r'\bpowerful sound\b','sonido potente'),
        (r'\bbattery life\b','autonomía'),
        (r'\bwith\b','con'),
        (r'\band\b','y')]
    for pat,rep in replacements:t=re.sub(pat,rep,t,flags=re.I)
    return t[:1200]

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
    if base:
        base_es=_translate_base_description(base) if _smart_looks_english(base) else base
        if suffix:return Derived((base_es.rstrip('. ')+'. Especificaciones verificadas: '+suffix+'.')[:2400],min(.98,max(.91,base_q+.04)),'spanish_description_plus_verified_specs',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
        return Derived(base_es,min(.95,max(.88,base_q)),'spanish_description',base_ev.source_url,base_ev.attribute,base_ev.raw_value)
    if suffix:return Derived(f'{name}. Especificaciones verificadas: {suffix}.',.91,'spanish_verified_specs_description')
    return Derived(reason='description_not_found')


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
    return Derived(reason='description_not_found')
