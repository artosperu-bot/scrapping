from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
TARGET = ROOT / "src/product_intelligence/price_discovery.py"


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one patch target, got {count}: {old[:120]!r}")
    return text.replace(old, new, 1)


text = TARGET.read_text(encoding="utf-8")
old = '''        context = text[start:end].casefold()\n        if any(marker in context for marker in _NON_PRODUCT_PRICE_CONTEXT):\n            continue\n        positive = sum(1 for marker in _PRODUCT_PRICE_CONTEXT if marker in context)\n'''
new = '''        context = text[start:end].casefold()\n        if any(marker in context for marker in _NON_PRODUCT_PRICE_CONTEXT):\n            continue\n        # Some commerce templates render a reference/unit value as\n        # ``SKU: 0.2kg S/ 16.92`` (or alongside an ``N un = X kg`` ratio).\n        # This is not the product selling price. Keep the guard deliberately\n        # narrower than a generic "weight before price" rule so normal products\n        # such as "1L S/ 10" remain eligible.\n        prefix = text[max(0, match.start() - 96):match.start()].casefold()\n        sku_weight = re.search(\n            r"\\bsku\\s*:\\s*\\d+(?:[.,]\\d+)?\\s*(?:kg|g|gr|lb|l|ml)\\s*$",\n            prefix,\n            re.I,\n        )\n        unit_ratio = re.search(\n            r"\\b\\d+\\s*(?:un|und|unidad(?:es)?)\\s*=\\s*\\d+(?:[.,]\\d+)?\\s*(?:kg|g|gr|lb|l|ml)\\b",\n            prefix,\n            re.I,\n        )\n        if sku_weight or unit_ratio:\n            continue\n        positive = sum(1 for marker in _PRODUCT_PRICE_CONTEXT if marker in context)\n'''
text = replace_once(text, old, new)
TARGET.write_text(text, encoding="utf-8")
print("P7_WEIGHT_REFERENCE_PRICE_PATCH=APPLIED")
