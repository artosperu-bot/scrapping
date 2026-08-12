from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def patch(path,old,new,count=1):
    p=ROOT/path;s=p.read_text(encoding='utf-8')
    if old not in s: raise SystemExit(f'anchor missing {path}: {old[:90]}')
    p.write_text(s.replace(old,new,count),encoding='utf-8')

# batch imports
patch('src/product_intelligence/batch.py','from .ai_enrichment import AIConfig\n','from .ai_enrichment import AIConfig\nfrom .ai_discovery import discover_official_urls\nfrom .input_identity import parse_product_query\n')

# replace legacy manual items with generic identity queries while retaining compatibility
start='def manual_items(template: str, part_numbers: list[str]) -> list[BatchItem]:\n'
end='\n\ndef _meaningful_product_tokens'
p=ROOT/'src/product_intelligence/batch.py';s=p.read_text(encoding='utf-8');a=s.index(start);b=s.index(end,a)
replacement='''def manual_identity_items(template: str, identities: list[ProductIdentity]) -> list[BatchItem]:\n    """Bind generic product identities to product rows. One strong value/name is enough."""\n    sheet, header_row = _best_product_sheet(template)\n    return [BatchItem(header_row + i + 1, sheet, ident) for i, ident in enumerate(identities)]\n\n\ndef manual_items(template: str, part_numbers: list[str]) -> list[BatchItem]:\n    """Backward-compatible MPN wrapper for CLI/API callers."""\n    identities=[]\n    for value in part_numbers:\n        ident=parse_product_query(str(value))\n        if ident: identities.append(ident)\n    return manual_identity_items(template,identities)\n'''
s=s[:a]+replacement+s[b:];p.write_text(s,encoding='utf-8')

# scrape_item gets AI config
patch('src/product_intelligence/batch.py','def scrape_item(item: BatchItem, out_dir: str, template_plan: dict | None = None, log=lambda m: None) -> ProductRecord | None:\n','def scrape_item(item: BatchItem, out_dir: str, template_plan: dict | None = None, ai_config: AIConfig | None = None, log=lambda m: None) -> ProductRecord | None:\n')

# AI discovery only if normal discovery did not find a likely official candidate
patch('src/product_intelligence/batch.py','''    candidates = [type("Candidate", (), {"url": item.source_url, "likely_official": True, "score": 1.0})()] if item.source_url else search_web(item.identity, limit=12)\n    media_slots = int((template_plan or {}).get("media_slots", 0) or 0)\n''','''    candidates = [type("Candidate", (), {"url": item.source_url, "likely_official": True, "score": 1.0, "ai_assisted": False})()] if item.source_url else search_web(item.identity, limit=16)\n    if ai_config and ai_config.discovery_enabled and not any(bool(getattr(c,"likely_official",False)) for c in candidates):\n        ai_urls=discover_official_urls(item.identity,ai_config)\n        if ai_urls:\n            log(f"  IA web discovery: {len(ai_urls)} URLs candidatas; todas se validarán con el scraper")\n            known={getattr(c,"url","") for c in candidates}\n            for aic in ai_urls:\n                if aic.url in known: continue\n                candidates.append(type("Candidate",(),{"url":aic.url,"likely_official":False,"score":aic.confidence,"ai_assisted":True})())\n                known.add(aic.url)\n    media_slots = int((template_plan or {}).get("media_slots", 0) or 0)\n''')

# If AI found an exact candidate, only promote it to manufacturer after brand-host proof.
patch('src/product_intelligence/batch.py','''            if rec.identity.identifiers_conflicting:\n                raise ValueError("identificadores en conflicto")\n            if accepted and not _cross_source_consistent(accepted[0], rec, candidate.url):\n''','''            if rec.identity.identifiers_conflicting:\n                raise ValueError("identificadores en conflicto")\n            if getattr(candidate,"ai_assisted",False) and (rec.fetch or {}).get("source_class") != "manufacturer":\n                learned_brand=re.sub(r"[^a-z0-9]","",key_norm(rec.identity.brand or ""))\n                host_compact=re.sub(r"[^a-z0-9]","",key_norm(host))\n                if learned_brand and learned_brand in host_compact:\n                    rec=pipe.process_url(item.identity,candidate.url,official_domain=host,include_pdfs=include_pdfs,include_images=include_images,browser_fallback=True,target_semantics=target_semantics,media_slots=media_slots)\n            if accepted and not _cross_source_consistent(accepted[0], rec, candidate.url):\n''')

# run_batch accepts generic identities
patch('src/product_intelligence/batch.py','''    ai_config: AIConfig | None = None,\n    manual_part_numbers: list[str] | None = None,\n) -> dict:\n''','''    ai_config: AIConfig | None = None,\n    manual_part_numbers: list[str] | None = None,\n    manual_identities: list[ProductIdentity] | None = None,\n) -> dict:\n''')
patch('src/product_intelligence/batch.py','''    manual_mode = bool(manual_part_numbers)\n    items = manual_items(template, manual_part_numbers or []) if manual_mode else detect_items(template)\n    log(f"Productos a procesar: {len(items)}" + (" (part numbers manuales)" if manual_mode else " (detectados en Excel)"))\n''','''    manual_mode = bool(manual_identities or manual_part_numbers)\n    if manual_identities:\n        items=manual_identity_items(template,manual_identities)\n    elif manual_part_numbers:\n        items=manual_items(template,manual_part_numbers)\n    else:\n        items=detect_items(template)\n    log(f"Productos a procesar: {len(items)}" + (" (entradas manuales: MPN/EAN/UPC/GTIN/nombre)" if manual_mode else " (detectados en Excel)"))\n''')
patch('src/product_intelligence/batch.py','rec = scrape_item(item, str(out / "json"), template_plan=template_plan, log=log)','rec = scrape_item(item, str(out / "json"), template_plan=template_plan, ai_config=ai_config, log=log)')
patch('src/product_intelligence/batch.py','"mode": "manual_part_numbers" if manual_mode else "excel_detected",','"mode": "manual_product_identity" if manual_mode else "excel_detected",')

# media source provenance and manufacturer preference
patch('src/product_intelligence/pipeline.py','''        rec.media = media\n        # Excel-safe default: only exact product/variant media is auto-fill eligible.\n''','''        for _m in media:\n            _m["source_class"] = source_class\n            _m["source_page"] = fetch.final_url\n        rec.media = media\n        # Excel-safe default: only exact product/variant media is auto-fill eligible.\n''')
patch('src/product_intelligence/marketplace_mapper.py','''    return (\n        scope_rank.get(str(item.get("scope")), 0),\n        identity_rank,\n''','''    source_class_rank={"manufacturer":3,"secondary":2,"marketplace":1}.get(str(item.get("source_class") or ""),0)\n    return (\n        scope_rank.get(str(item.get("scope")), 0),\n        source_class_rank,\n        identity_rank,\n''')

# tests
(ROOT/'tests/test_multi_input_ai_discovery.py').write_text('''from product_intelligence.input_identity import parse_product_query\nfrom product_intelligence.model_catalog import capability\n\ndef test_primary_identifier_autodetection():\n    assert parse_product_query("JBLENDURRUN3BTBAM").mpn=="JBLENDURRUN3BTBAM"\n    assert parse_product_query("123456789012").upc=="123456789012"\n    assert parse_product_query("1234567890123").ean=="1234567890123"\n    assert parse_product_query("JBL Tune 530C USB-C").product_name=="JBL Tune 530C USB-C"\n\ndef test_optional_hints_strengthen_identity():\n    i=parse_product_query("JBLENDURRUN3BTBAM | brand=JBL | color=Azul")\n    assert i.mpn=="JBLENDURRUN3BTBAM" and i.brand=="JBL" and i.color=="Azul"\n\ndef test_web_capability_is_provider_specific():\n    assert capability("openai","gpt-5-mini-2025-08-07").web_discovery\n    assert capability("openrouter","mistralai/mistral-small").web_discovery\n    assert not capability("ollama","mistral").web_discovery\n''',encoding='utf-8')

print('multi-input AI discovery patch applied')
