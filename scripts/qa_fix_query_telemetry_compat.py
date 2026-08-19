from pathlib import Path

path = Path("src/product_intelligence/price_peru_coverage.py")
text = path.read_text(encoding="utf-8")
old = '''    specs = _query_specs(identity, domain)
    for index, (query, signal_type) in enumerate(specs):
'''
new = '''    signal_map = {query: signal for query, signal in _query_specs(identity, domain)}
    specs = [(query, signal_map.get(query, "UNKNOWN_SIGNAL")) for query in _queries(identity, domain)]
    for index, (query, signal_type) in enumerate(specs):
'''
if old not in text:
    if new in text:
        print("QUERY_TELEMETRY_COMPAT_ALREADY_APPLIED=1")
        raise SystemExit(0)
    raise SystemExit("query telemetry compatibility target not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("QUERY_TELEMETRY_COMPAT_PATCH=APPLIED")
