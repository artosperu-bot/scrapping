from pathlib import Path
p=Path('src/product_intelligence/batch.py')
s=p.read_text(encoding='utf-8')
old='''    errors: list[str] = []
    accepted: list[ProductRecord] = []

    for candidate in candidates:
        try:
'''
new='''    errors: list[str] = []
    accepted: list[ProductRecord] = []
    queue=list(candidates)
    seen_urls={getattr(c,"url","") for c in queue}
    manufacturer_followup_done=False
    cursor=0

    while cursor < len(queue):
        candidate=queue[cursor]
        cursor += 1
        try:
'''
if old not in s: raise SystemExit('loop anchor missing')
s=s.replace(old,new,1)
old='''            accepted.append(rec)
            log(f"  fuente validada: {(rec.fetch or {}).get('source_class', '?')} / {rec.identity.match_level}")
            has_manufacturer = any((r.fetch or {}).get("source_class") == "manufacturer" for r in accepted)
            if len(accepted) >= 3 or (has_manufacturer and len(accepted) >= 2):
                break
'''
new='''            accepted.append(rec)
            log(f"  fuente validada: {(rec.fetch or {}).get('source_class', '?')} / {rec.identity.match_level}")

            # A manual MPN often starts without a brand. Once the first exact source teaches us
            # the brand/model, do a second discovery pass with that richer identity so official
            # regional manufacturer pages can outrank retailers. This remains fully generic.
            if not manufacturer_followup_done:
                learned_brand=rec.identity.brand or item.identity.brand
                learned_model=rec.identity.model or rec.identity.product_name or item.identity.model
                if learned_brand and (item.identity.mpn or item.identity.ean or item.identity.upc or item.identity.gtin):
                    enriched=ProductIdentity(
                        mpn=item.identity.mpn or rec.identity.mpn,
                        ean=item.identity.ean or rec.identity.ean,
                        upc=item.identity.upc or rec.identity.upc,
                        gtin=item.identity.gtin or rec.identity.gtin,
                        brand=learned_brand,
                        model=learned_model,
                    )
                    followups=search_web(enriched,limit=12)
                    # Likely manufacturer candidates go next, before remaining secondary sources.
                    fresh=[c for c in followups if c.url not in seen_urls]
                    for c in fresh: seen_urls.add(c.url)
                    fresh.sort(key=lambda c:(not bool(getattr(c,"likely_official",False)),-float(getattr(c,"score",0))))
                    queue[cursor:cursor]=fresh
                manufacturer_followup_done=True

            has_manufacturer = any((r.fetch or {}).get("source_class") == "manufacturer" for r in accepted)
            # Prefer manufacturer evidence whenever discoverable. Do not stop merely because three
            # retailers were accepted; allow the enriched follow-up queue to be tried first.
            if has_manufacturer and len(accepted) >= 2:
                break
            if len(accepted) >= 5:
                break
'''
if old not in s: raise SystemExit('accepted anchor missing')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('patched manufacturer discovery')
