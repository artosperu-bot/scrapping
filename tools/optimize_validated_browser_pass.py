from pathlib import Path
p=Path('src/product_intelligence/pipeline.py')
s=p.read_text(encoding='utf-8')
s=s.replace('from .web_fetch import fetch_page','from .web_fetch import fetch_page, fetch_browser',1)
s=s.replace('''        fetch = fetch_page(
            url, browser_fallback=browser_fallback,
            prefer_browser=bool(media_slots > 1),
            activate_lazy_media=bool(media_slots > 1),
        )
''','''        # Fast identity preflight first. A rich Chromium pass is expensive and should run
        # only after this URL has proved that it is the requested product.
        fetch = fetch_page(url, browser_fallback=browser_fallback)
''',1)
anchor='''        if candidate.match_level not in required:
            raise ValueError(
                f"Fuente rechazada: clase={source_class}, identidad={candidate.match_level}, "
                f"confirmados={candidate.identifiers_confirmed}, conflictos={candidate.identifiers_conflicting}"
            )

'''
insert='''        if candidate.match_level not in required:
            raise ValueError(
                f"Fuente rechazada: clase={source_class}, identidad={candidate.match_level}, "
                f"confirmados={candidate.identifiers_confirmed}, conflictos={candidate.identifiers_conflicting}"
            )

        # Once identity is proven, enrich the same public product page with a normal browser
        # when the Excel asks for a gallery. This activates lazy-loaded images and captures
        # JSON/XHR/media without spending Chromium time on rejected search candidates.
        if media_slots > 1 and fetch.method != "playwright":
            try:
                rich = fetch_browser(fetch.final_url, timeout=45, activate_lazy_media=True)
                if rich.status_code and rich.status_code < 400:
                    fetch = rich
                    page = extract_page(fetch.html, fetch.final_url, [x for x in terms if x])
                    rich_candidate = identity_from_page(page, expected=expected, source_url=fetch.final_url)
                    if source_class == "manufacturer" and expected.mpn and not rich_candidate.mpn and rich_candidate.sku:
                        rich_candidate.mpn = rich_candidate.sku
                    rich_candidate = compare_identity(expected, rich_candidate)
                    if rich_candidate.match_level in required:
                        candidate = rich_candidate
            except Exception as exc:
                fetch.warnings.append(f"validated_browser_enrichment_failed:{type(exc).__name__}")

'''
if anchor not in s: raise SystemExit('anchor missing')
s=s.replace(anchor,insert,1)
p.write_text(s,encoding='utf-8')
print('patched')
