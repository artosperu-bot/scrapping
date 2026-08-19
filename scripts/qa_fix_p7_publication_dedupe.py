from pathlib import Path

path = Path("src/product_intelligence/price_identity.py")
text = path.read_text(encoding="utf-8")

old = '''def dedupe_offers(offers: list[PriceOffer]) -> list[PriceOffer]:
    best: dict[tuple, PriceOffer] = {}
    for row in offers:
        canonical = _canonical_url(row.url)
        specific_pdp = bool((urlsplit(row.url).path or "").strip("/"))
        locator = canonical if specific_pdp else (row.publication_id or row.sku or canonical)
        key = (_norm(row.channel), competitor_key(row), _norm(row.part_number or row.model), locator)
        current = best.get(key)
'''

new = '''def _numeric_publication_route(url: str) -> str | None:
    parsed = urlsplit(url)
    path = parsed.path or ""
    match = re.search(r"/(product|producto|products|p)/(\\d{3,})(?:[-/]|$)", path, re.I)
    if not match:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    marker = match.group(1).lower()
    return f"route:{host}:{marker}:{match.group(2)}"


def dedupe_offers(offers: list[PriceOffer]) -> list[PriceOffer]:
    best: dict[tuple, PriceOffer] = {}
    for row in offers:
        canonical = _canonical_url(row.url)
        specific_pdp = bool((urlsplit(row.url).path or "").strip("/"))
        route_locator = _numeric_publication_route(row.url)
        locator = route_locator or (canonical if specific_pdp else (row.publication_id or row.sku or canonical))
        key = (_norm(row.channel), competitor_key(row), _norm(row.part_number or row.model), locator)
        current = best.get(key)
'''

if new in text:
    print("P7 numeric publication-route dedupe patch already present")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("P7 numeric publication-route dedupe patch applied")
else:
    raise SystemExit("expected dedupe block not found; refusing broad rewrite")
