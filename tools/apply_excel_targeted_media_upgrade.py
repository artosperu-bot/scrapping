from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def patch(path, old, new, count=1):
    p=ROOT/path
    s=p.read_text(encoding='utf-8')
    if old not in s:
        raise SystemExit(f'anchor not found: {path}: {old[:100]}')
    s=s.replace(old,new,count)
    p.write_text(s,encoding='utf-8')

# 1) Browser may be explicitly preferred for rich gallery capture and activates lazy assets by scrolling.
patch('src/product_intelligence/web_fetch.py',
'''def fetch_browser(url: str, timeout: int = 45, capture_json: bool = True) -> FetchResult:\n''',
'''def fetch_browser(url: str, timeout: int = 45, capture_json: bool = True, activate_lazy_media: bool = False) -> FetchResult:\n''')
patch('src/product_intelligence/web_fetch.py',
'''        try:\n            page.wait_for_load_state("networkidle", timeout=min(timeout, 12) * 1000)\n        except Exception:\n            warnings.append("networkidle_timeout")\n        html = page.content()\n''',
'''        try:\n            page.wait_for_load_state("networkidle", timeout=min(timeout, 12) * 1000)\n        except Exception:\n            warnings.append("networkidle_timeout")\n        if activate_lazy_media:\n            try:\n                page.evaluate("""async () => {\n                    const step = Math.max(600, Math.floor(window.innerHeight * 0.8));\n                    const maxY = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);\n                    for (let y = 0; y < maxY; y += step) {\n                        window.scrollTo(0, y);\n                        await new Promise(r => setTimeout(r, 90));\n                    }\n                    window.scrollTo(0, 0);\n                }""")\n                page.wait_for_timeout(500)\n            except Exception:\n                warnings.append("lazy_media_activation_failed")\n        html = page.content()\n''')
patch('src/product_intelligence/web_fetch.py',
'''def fetch_page(url: str, timeout: int = 30, browser_fallback: bool = True) -> FetchResult:\n''',
'''def fetch_page(url: str, timeout: int = 30, browser_fallback: bool = True, prefer_browser: bool = False, activate_lazy_media: bool = False) -> FetchResult:\n''')
patch('src/product_intelligence/web_fetch.py',
'''    needs_browser = static.status_code in {401, 403, 429} or _looks_js_shell(static.html)\n    if browser_fallback and needs_browser:\n        try:\n            browser = fetch_browser(url, timeout=max(timeout, 40))\n            if browser.status_code and browser.status_code < 400 and len(browser.html) >= len(static.html):\n                browser.warnings.insert(0, f"static_status={static.status_code}")\n                return browser\n''',
'''    needs_browser = prefer_browser or static.status_code in {401, 403, 429} or _looks_js_shell(static.html)\n    if browser_fallback and needs_browser:\n        try:\n            browser = fetch_browser(url, timeout=max(timeout, 40), activate_lazy_media=activate_lazy_media)\n            browser_is_useful = browser.status_code and browser.status_code < 400 and (prefer_browser or len(browser.html) >= len(static.html))\n            if browser_is_useful:\n                browser.warnings.insert(0, f"static_status={static.status_code}")\n                return browser\n''')

# 2) Generic target-aware line extractor for fields requested by the Excel contract.
target_file=ROOT/'src/product_intelligence/target_extract.py'
target_file.write_text(r'''from __future__ import annotations

import re
from rapidfuzz import fuzz
from .models import Evidence
from .normalize import key_norm


def _phrase(value: str) -> str:
    value=re.sub(r'([a-z0-9])([A-Z])',r'\1 \2',str(value or ''))
    value=value.replace('_',' ').replace('-',' ')
    return key_norm(value)


def extract_target_evidence(text: str, targets: list[str] | None, source_url: str, source_type: str,
                            match_level: str, confidence: float) -> list[Evidence]:
    """Extract label/value evidence only for fields the Excel explicitly asks for.

    This does not invent category vocabulary. It compares page labels against arbitrary target
    names produced by the workbook contract, so a future template can request a field that this
    code has never seen before.
    """
    wanted=[(str(t),_phrase(str(t))) for t in (targets or []) if len(_phrase(str(t)))>=3]
    if not wanted:
        return []
    lines=[re.sub(r'\s+',' ',x).strip() for x in (text or '').splitlines() if x.strip()]
    out=[]; seen=set()
    for i,line in enumerate(lines):
        # Explicit separators are safest for generic, previously unseen attributes.
        m=re.match(r'^(.{2,120}?)(?:\s*[:=]\s+|\s{2,})(.{1,300})$',line)
        left=m.group(1).strip() if m else line
        right=m.group(2).strip() if m else None
        nl=_phrase(left)
        for original,target in wanted:
            score=fuzz.ratio(nl,target)/100
            contained=(target in nl or nl in target) and min(len(nl),len(target))>=4
            if score < .86 and not contained:
                continue
            value=right
            selector='target_label_value'
            if not value and score>=.94 and i+1<len(lines):
                nxt=lines[i+1]
                # Do not use the next line when it itself looks like another short label.
                if len(nxt)<=300 and not re.fullmatch(r'[\w áéíóúñÁÉÍÓÚÑ()/#.-]{2,80}:?',nxt):
                    value=nxt; selector='target_next_line'
                elif re.search(r'\d|sí|si|yes|no|true|false|bluetooth|usb|ip\d',nxt,re.I):
                    value=nxt; selector='target_next_line'
            if value in (None,''):
                continue
            key=(key_norm(original),key_norm(value))
            if key in seen: continue
            seen.add(key)
            out.append(Evidence(attribute=original,raw_value=value,normalized_value=value,
                                source_url=source_url,source_type=source_type,selector=selector,
                                match_level=match_level,confidence=min(.97,confidence)))
    return out
''',encoding='utf-8')

# 3) Pipeline receives workbook targets and media slots; force rich browser only when the template needs it.
patch('src/product_intelligence/pipeline.py',
'''from .evidence_graph import build_evidence_graph\n''',
'''from .evidence_graph import build_evidence_graph\nfrom .target_extract import extract_target_evidence\n''')
patch('src/product_intelligence/pipeline.py',
'''        browser_fallback: bool = True,\n    ) -> ProductRecord:\n        fetch = fetch_page(url, browser_fallback=browser_fallback)\n''',
'''        browser_fallback: bool = True,\n        target_semantics: list[str] | None = None,\n        media_slots: int = 0,\n    ) -> ProductRecord:\n        fetch = fetch_page(\n            url, browser_fallback=browser_fallback,\n            prefer_browser=bool(media_slots > 1),\n            activate_lazy_media=bool(media_slots > 1),\n        )\n''')
patch('src/product_intelligence/pipeline.py',
'''        evidence += extract_text_evidence(page.get("text", ""), fetch.final_url, html_type, candidate.match_level, max(.60, base-.08), expected_capacity=candidate.capacity or expected.capacity)\n''',
'''        evidence += extract_text_evidence(page.get("text", ""), fetch.final_url, html_type, candidate.match_level, max(.60, base-.08), expected_capacity=candidate.capacity or expected.capacity)\n        evidence += extract_target_evidence(\n            page.get("text", ""), target_semantics, fetch.final_url, html_type,\n            candidate.match_level, max(.60, base-.06),\n        )\n''')
patch('src/product_intelligence/pipeline.py',
'''                    evidence.extend(extract_text_evidence(pdf_text, pdf, "official_pdf", candidate.match_level, min(base,.95,pconf), expected_capacity=candidate.capacity or expected.capacity))\n''',
'''                    evidence.extend(extract_text_evidence(pdf_text, pdf, "official_pdf", candidate.match_level, min(base,.95,pconf), expected_capacity=candidate.capacity or expected.capacity))\n                    evidence.extend(extract_target_evidence(\n                        pdf_text, target_semantics, pdf, "official_pdf", candidate.match_level, min(base,.94,pconf)\n                    ))\n''')
patch('src/product_intelligence/pipeline.py',
'''            "raw_source_evidence": sum(1 for e in rec.evidence if e.source_type == "official_source_html"),\n''',
'''            "raw_source_evidence": sum(1 for e in rec.evidence if e.source_type == "official_source_html"),\n            "target_semantics_requested": list(target_semantics or []),\n            "media_slots_requested": int(media_slots or 0),\n''')

# 4) Batch actually passes the Excel contract into the extractor.
patch('src/product_intelligence/batch.py',
'''    include_images = bool((template_plan or {}).get("media_slots", 0))\n    include_pdfs = bool((template_plan or {}).get("summary", {}).get("scrape_targets", 1))\n''',
'''    media_slots = int((template_plan or {}).get("media_slots", 0) or 0)\n    target_semantics = list((template_plan or {}).get("scrape_semantics") or [])\n    include_images = bool(media_slots)\n    include_pdfs = bool((template_plan or {}).get("summary", {}).get("scrape_targets", 1))\n''')
patch('src/product_intelligence/batch.py',
'''                browser_fallback=True,\n            )\n''',
'''                browser_fallback=True,\n                target_semantics=target_semantics,\n                media_slots=media_slots,\n            )\n''')

# 5) Media discovery: broader lazy/gallery attributes + JSON application state + inline-script URLs.
p=ROOT/'src/product_intelligence/media_discovery.py'
s=p.read_text(encoding='utf-8')
s=s.replace('''    if source.startswith("jsonld:Product.image") or source.startswith("meta:og:image"):\n        return "product_gallery", True\n''','''    if source.startswith("jsonld:Product.image") or source.startswith("meta:og:image"):\n        return "product_gallery", True\n    if source.startswith("json:") and re.search(r"image|gallery|media|asset|picture|photo", hay, re.I):\n        return "product_gallery", True\n''',1)
s=s.replace('''        for attr in ["src", "data-src", "data-original", "data-zoom-image", "data-large-image"]:\n            add(img.get(attr), f"dom:{attr}", tag_hint="image", alt=alt)\n''','''        parent_ctx=" ".join([str(img.get("class") or ""), str(img.get("id") or ""), str(getattr(img.parent,"attrs",{}).get("class","") if getattr(img,"parent",None) else "")])\n        for attr in ["src", "data-src", "data-original", "data-original-src", "data-zoom", "data-zoom-image", "data-large", "data-large-image", "data-full", "data-image"]:\n            add(img.get(attr), f"dom:{attr}:{parent_ctx}", tag_hint="image", alt=alt, surrounding_text=parent_ctx)\n''',1)
anchor='''    # Browser/network discovered public assets. Provenance is the validated product page.\n'''
extra=r'''    # Generic embedded application JSON/state. This is common in modern storefronts where the
    # visible gallery is backed by a JSON array rather than individual <img> tags.
    def walk_media_json(obj, path="root", context=""):
        if isinstance(obj, dict):
            ctx_parts=[]
            for k in ["name","title","productName","sku","mpn","id","color","variant","model"]:
                v=obj.get(k)
                if isinstance(v,(str,int,float)):
                    ctx_parts.append(f"{k}={v}")
            local_ctx=" ".join([context,*ctx_parts])[-1200:]
            for k,v in obj.items():
                pth=f"{path}.{k}"
                if isinstance(v,str) and _media_type(v)=="image" and re.search(r"image|img|gallery|media|asset|photo|picture|src|url",str(k),re.I):
                    add(v,f"json:{pth}",tag_hint="image",surrounding_text=local_ctx)
                elif isinstance(v,(dict,list)):
                    walk_media_json(v,pth,local_ctx)
        elif isinstance(obj,list):
            for idx,v in enumerate(obj[:500]):
                walk_media_json(v,f"{path}[{idx}]",context)

    for script in soup.find_all("script"):
        typ=(script.get("type") or "").lower()
        raw=script.string or script.get_text(" ",strip=False) or ""
        if not raw or len(raw)>5_000_000:
            continue
        if "json" in typ or script.get("id") in {"__NEXT_DATA__","__NUXT_DATA__"}:
            try:
                walk_media_json(json.loads(raw),f"script:{script.get('id') or typ or 'json'}")
            except Exception:
                pass
        # Last-resort public source scan for explicit image URLs inside JS configuration.
        # Identity validation below prevents unrelated page assets from being auto-filled.
        for m in re.finditer(r'''["'](https?:\\?/\\?/[^"']+?\.(?:jpe?g|png|webp|avif))(?:\\?[^"']*)?["']''',raw,re.I):
            val=m.group(1).replace('\\/','/')
            near=raw[max(0,m.start()-350):min(len(raw),m.end()+350)]
            add(val,"json:inline_script_image",tag_hint="image",surrounding_text=near)

    # Gallery zoom links sometimes carry the highest-resolution asset.
    for link in soup.find_all("a",href=True):
        href=link.get("href")
        ctx=" ".join([str(link.get("class") or ""),str(link.get("id") or ""),link.get_text(" ",strip=True)[:120]])
        if _media_type(urljoin(base_url,href))=="image" and (link.find("img") is not None or re.search(r"gallery|zoom|product|image",ctx,re.I)):
            add(href,f"dom:a:href:{ctx}",tag_hint="image",surrounding_text=ctx)

'''
if anchor not in s: raise SystemExit('media anchor missing')
s=s.replace(anchor,extra+anchor,1)
p.write_text(s,encoding='utf-8')

# 6) Connectivity: never convert charging-only USB into audio/data connectivity.
p=ROOT/'src/product_intelligence/field_derivations.py'
s=p.read_text(encoding='utf-8')
start=s.index('def derive_connectivity(')
end=s.index('\ndef derive_headphone_type(',start)
new=r'''def derive_connectivity(rec: ProductRecord, options: list[Any]) -> Derived:
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

'''
s=s[:start]+new+s[end:]
p.write_text(s,encoding='utf-8')

# 7) Mapper uses the workbook contract also for previously unseen technical fields.
p=ROOT/'src/product_intelligence/excel_mapper_v8.py'
s=p.read_text(encoding='utf-8')
s=s.replace('''from .template_intelligence import classify_field\n''','''from .template_intelligence import classify_field\nfrom .template_contract import analyze_template_contract\n''',1)
s=s.replace('''    wb=load_workbook(template)\n    options_idx=_build_option_index(wb)\n''','''    wb=load_workbook(template)\n    template_plan=analyze_template_contract(template)\n    target_lookup={(f["sheet"],f["column"]):f for sh in template_plan.get("sheets",[]) for f in sh.get("fields",[])}\n    options_idx=_build_option_index(wb)\n''',1)
s=s.replace('''                if field_class=='SELLER_DATA':\n                    continue\n''','''                plan_field=target_lookup.get((ws.title,c),{})\n                if field_class=='SELLER_DATA' or plan_field.get("role") in {"SELLER_INPUT","MARKETPLACE_INPUT","DERIVED_OUTPUT"}:\n                    continue\n''',1)
s=s.replace('''                # Strict evidence resolver scans ALL clean evidence, including former additional_attributes.\n                if key:\n                    cand=best_candidate(rec,header,str(desc) if desc else None,key,contracts[c])\n''','''                # Strict evidence resolver scans ALL clean evidence. For a previously unseen technical\n                # field, the Excel contract itself supplies the semantic target instead of requiring\n                # a hardcoded category dictionary entry.\n                resolver_key=key or plan_field.get("semantic") or plan_field.get("canonical")\n                if not resolver_key and plan_field.get("role")=="SCRAPE_TARGET":\n                    resolver_key=_strip_field_id(header)\n                if resolver_key:\n                    cand=best_candidate(rec,header,str(desc) if desc else None,resolver_key,contracts[c])\n''',1)
s=s.replace('''                        written.append({"sheet":ws.title,"cell":cell.coordinate,"header":header,"attribute":key,"value":value,"source":cand.evidence.source_url,''','''                        written.append({"sheet":ws.title,"cell":cell.coordinate,"header":header,"attribute":resolver_key,"value":value,"source":cand.evidence.source_url,''',1)
p.write_text(s,encoding='utf-8')

# 8) Regression tests.
test=ROOT/'tests/test_targeted_excel_and_media.py'
test.write_text(r'''from product_intelligence.models import ProductRecord, ProductIdentity, Evidence
from product_intelligence.field_derivations import derive_connectivity
from product_intelligence.target_extract import extract_target_evidence


def test_target_extract_supports_never_seen_excel_semantic():
    text="Velocidad máxima: 320 km/h\nOtro dato: X"
    ev=extract_target_evidence(text,["VelocidadMaxima"],"https://example.test/p","official_html","EXACT",.95)
    assert ev and ev[0].attribute=="VelocidadMaxima" and "320" in str(ev[0].raw_value)


def test_connectivity_does_not_treat_charging_usb_as_audio_connectivity():
    rec=ProductRecord(identity=ProductIdentity(product_name="Wireless headset",match_level="EXACT"),evidence=[
        Evidence(attribute="Charging Input",raw_value="USB-C",normalized_value="USB-C",source_url="x",source_type="official_html",match_level="EXACT",confidence=.98),
        Evidence(attribute="Wireless",raw_value="2.4 GHz Radio/RF",normalized_value="2.4 GHz Radio/RF",source_url="x",source_type="official_html",match_level="EXACT",confidence=.98),
    ])
    d=derive_connectivity(rec,["USB-C","Inalámbrico","Radiofrecuencia (RF)"])
    assert "USB-C" not in str(d.value)
    assert "Inalámbrico" in str(d.value)


def test_connectivity_keeps_usb_c_when_audio_connector_proves_it():
    rec=ProductRecord(identity=ProductIdentity(product_name="Wired headset",match_level="EXACT"),evidence=[
        Evidence(attribute="Audio Connector",raw_value="1x USB-C",normalized_value="1x USB-C",source_url="x",source_type="official_html",match_level="EXACT",confidence=.98),
    ])
    d=derive_connectivity(rec,["USB-C","Inalámbrico"])
    assert d.value=="USB-C"
''',encoding='utf-8')
print('upgrade applied')
