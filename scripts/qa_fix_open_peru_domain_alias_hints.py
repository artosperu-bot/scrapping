from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
TARGET = ROOT / "src/product_intelligence/price_peru_coverage.py"


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one patch target, got {count}: {old[:120]!r}")
    return text.replace(old, new, 1)


text = TARGET.read_text(encoding="utf-8")

old = '''        learned = tuple(dict.fromkeys(str(domain or "").strip().casefold().removeprefix("www.") for domain in priority_domains if str(domain or "").strip()))[:12]\n        specs += [(f'"{strong}" site:{domain}', "LEARNED_DOMAIN") for domain in learned]\n        specs += [(f'"{strong}" site:{domain}', "KNOWN_DOMAIN_HINT") for domain in PERU_RETAIL_HINT_DOMAINS]\n'''

new = '''        learned = tuple(dict.fromkeys(str(domain or "").strip().casefold().removeprefix("www.") for domain in priority_domains if str(domain or "").strip()))[:12]\n        # Reuse the same bounded MPN alias family that the directed lane already\n        # trusts. This prevents exact-separator indexing differences from hiding\n        # a PDP inside a domain we already know, without expanding the source oracle.\n        domain_signals = [row for row in plan if str(row.signal_type).startswith("MPN_")][:3]\n        if not domain_signals:\n            domain_signals = list(plan[:1])\n        for domain in learned:\n            for index, row in enumerate(domain_signals):\n                signal_type = "LEARNED_DOMAIN" if index == 0 else f"LEARNED_DOMAIN_{row.signal_type}"\n                specs.append((f'"{row.query}" site:{domain}', signal_type))\n        for domain in PERU_RETAIL_HINT_DOMAINS:\n            for index, row in enumerate(domain_signals):\n                signal_type = "KNOWN_DOMAIN_HINT" if index == 0 else f"KNOWN_DOMAIN_HINT_{row.signal_type}"\n                specs.append((f'"{row.query}" site:{domain}', signal_type))\n'''

text = replace_once(text, old, new)
TARGET.write_text(text, encoding="utf-8")
print("OPEN_PERU_DOMAIN_ALIAS_HINTS_PATCH=APPLIED")
