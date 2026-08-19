from pathlib import Path

path = Path("src/product_intelligence/price_peru_coverage.py")
text = path.read_text(encoding="utf-8")

old = '''    local = host.endswith(".pe") or host.endswith(".com.pe")
    hinted = any(_host_matches(url, domain) for domain in (*PERU_RETAIL_HINT_DOMAINS, *priority_domains))
    peru_path = path.startswith("/peru")
    if not (local or hinted or peru_path): return False
'''
new = '''    local = host.endswith(".pe") or host.endswith(".com.pe")
    # Some Peru retailers use a generic .com while carrying an explicit Peru cue
    # in the hostname. This is geography evidence only; the existing strong-ID /
    # product-marker gate below still decides whether the URL is a product candidate.
    peru_host = "peru" in host
    hinted = any(_host_matches(url, domain) for domain in (*PERU_RETAIL_HINT_DOMAINS, *priority_domains))
    peru_path = path.startswith("/peru")
    if not (local or peru_host or hinted or peru_path): return False
'''

if new in text:
    print("P7 Peru-named dotcom admission patch already present")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("P7 Peru-named dotcom admission patch applied")
else:
    raise SystemExit("expected admission block not found; refusing broad rewrite")
