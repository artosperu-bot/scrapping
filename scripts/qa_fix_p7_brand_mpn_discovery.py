from pathlib import Path


path = Path("src/product_intelligence/price_peru_coverage.py")
text = path.read_text(encoding="utf-8")

old = '''        specs += [
            (f'"{strong}" site:.pe', "PERU_TLD_SCOPE"),
            (f'"{strong}" site:.com.pe', "PERU_TLD_SCOPE"),
        ]
        learned = tuple(dict.fromkeys(str(domain or "").strip().casefold().removeprefix("www.") for domain in priority_domains if str(domain or "").strip()))[:12]
'''

new = '''        specs += [
            (f'"{strong}" site:.pe', "PERU_TLD_SCOPE"),
            (f'"{strong}" site:.com.pe', "PERU_TLD_SCOPE"),
        ]
        # Price receives identity.brand only after the upstream identity bridge has
        # accepted an explicit valid brand or an evidence-backed resolved brand.
        # Add exactly two country-scope representations for the canonical MPN;
        # do not expand punctuation aliases or invent a brand when MPN is absent.
        canonical_mpn = str(identity.mpn or "").strip()
        if brand and canonical_mpn:
            specs += [
                (f'"{brand}" "{canonical_mpn}" site:.pe', "VERIFIED_BRAND_MPN_PERU_TLD_SCOPE"),
                (f'"{brand}" "{canonical_mpn}" site:.com.pe', "VERIFIED_BRAND_MPN_PERU_TLD_SCOPE"),
            ]
        learned = tuple(dict.fromkeys(str(domain or "").strip().casefold().removeprefix("www.") for domain in priority_domains if str(domain or "").strip()))[:12]
'''

if new in text:
    print("P7 brand+MPN country-scope patch already present")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("P7 brand+MPN country-scope patch applied")
else:
    raise SystemExit("expected country-scope block not found; refusing broad rewrite")
