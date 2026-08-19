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

anchor = '''def _search_query_batches(identity: ProductIdentity, queries: list[str], per_query: int) -> list[list[str]]:\n'''
helper = '''def _required_domain_from_query(query: str) -> str | None:\n    match = re.search(r"(?:^|\\s)site:([a-z0-9.-]+)", str(query or ""), flags=re.IGNORECASE)\n    if not match:\n        return None\n    return match.group(1).casefold().removeprefix("www.")\n\n\ndef _search_query_batches(identity: ProductIdentity, queries: list[str], per_query: int) -> list[list[str]]:\n'''
text = replace_once(text, anchor, helper)

old_batch = '''    def run(query: str) -> list[str]:\n        try:\n            return search_web_query(identity, query, limit=per_query, timeout=12)\n        except Exception:\n            return []\n'''
new_batch = '''    def run(query: str) -> list[str]:\n        urls, _metrics = _search_with_metrics(\n            identity, query, limit=per_query, required_domain=_required_domain_from_query(query)\n        )\n        return urls\n'''
text = replace_once(text, old_batch, new_batch)

old_specs = '''    def run(spec: tuple[str, str]):\n        query, signal_type = spec\n        urls, metrics = _search_with_metrics(identity, query, limit=per_query)\n        return query, signal_type, urls, metrics\n'''
new_specs = '''    def run(spec: tuple[str, str]):\n        query, signal_type = spec\n        urls, metrics = _search_with_metrics(\n            identity, query, limit=per_query, required_domain=_required_domain_from_query(query)\n        )\n        return query, signal_type, urls, metrics\n'''
text = replace_once(text, old_specs, new_specs)

TARGET.write_text(text, encoding="utf-8")
print("OPEN_PERU_SITE_DOMAIN_PATCH=APPLIED")
