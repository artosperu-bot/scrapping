from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
TARGET = ROOT / "src/product_intelligence/price_peru_coverage.py"


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one patch target, got {count}: {old[:80]!r}")
    return text.replace(old, new, 1)


text = TARGET.read_text(encoding="utf-8")

old_scope = '''    if strong:\n        learned = tuple(dict.fromkeys(str(domain or "").strip().casefold().removeprefix("www.") for domain in priority_domains if str(domain or "").strip()))[:12]\n        specs += [(f'"{strong}" site:{domain}', "LEARNED_DOMAIN") for domain in learned]\n        specs += [(f'"{strong}" site:{domain}', "KNOWN_DOMAIN_HINT") for domain in PERU_RETAIL_HINT_DOMAINS]\n'''
new_scope = '''    if strong:\n        # Country-scope discovery finds Peru retailers that are not yet known to\n        # capability memory or the static hint set. These are search-engine scopes,\n        # not one literal hostname, so admission remains identity + Peru constrained.\n        specs += [\n            (f'"{strong}" site:.pe', "PERU_TLD_SCOPE"),\n            (f'"{strong}" site:.com.pe', "PERU_TLD_SCOPE"),\n        ]\n        learned = tuple(dict.fromkeys(str(domain or "").strip().casefold().removeprefix("www.") for domain in priority_domains if str(domain or "").strip()))[:12]\n        specs += [(f'"{strong}" site:{domain}', "LEARNED_DOMAIN") for domain in learned]\n        specs += [(f'"{strong}" site:{domain}', "KNOWN_DOMAIN_HINT") for domain in PERU_RETAIL_HINT_DOMAINS]\n'''
text = replace_once(text, old_scope, new_scope)

old_helper = '''def _required_domain_from_query(query: str) -> str | None:\n    match = re.search(r"(?:^|\\s)site:([a-z0-9.-]+)", str(query or ""), flags=re.IGNORECASE)\n    if not match:\n        return None\n    return match.group(1).casefold().removeprefix("www.")\n'''
new_helper = '''def _required_domain_from_query(query: str) -> str | None:\n    match = re.search(r"(?:^|\\s)site:([a-z0-9.-]+)", str(query or ""), flags=re.IGNORECASE)\n    if not match:\n        return None\n    domain = match.group(1).casefold().removeprefix("www.")\n    # site:.pe / site:.com.pe are country-wide search scopes, not literal hosts.\n    if domain.startswith("."):\n        return None\n    return domain\n'''
text = replace_once(text, old_helper, new_helper)

TARGET.write_text(text, encoding="utf-8")
print("OPEN_PERU_TLD_SCOPE_PATCH=APPLIED")
