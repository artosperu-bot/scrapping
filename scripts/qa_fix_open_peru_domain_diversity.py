from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
TARGET = ROOT / "src/product_intelligence/price_peru_coverage.py"


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one patch target, got {count}: {old[:100]!r}")
    return text.replace(old, new, 1)


text = TARGET.read_text(encoding="utf-8")

old_helper = '''def _required_domain_from_query(query: str) -> str | None:\n    match = re.search(r"(?:^|\\s)site:([a-z0-9.-]+)", str(query or ""), flags=re.IGNORECASE)\n    if not match:\n        return None\n    domain = match.group(1).casefold().removeprefix("www.")\n    # site:.pe / site:.com.pe are country-wide search scopes, not literal hosts.\n    if domain.startswith("."):\n        return None\n    return domain\n\n\ndef _search_query_batches(identity: ProductIdentity, queries: list[str], per_query: int) -> list[list[str]]:\n'''
new_helper = '''def _required_domain_from_query(query: str) -> str | None:\n    match = re.search(r"(?:^|\\s)site:([a-z0-9.-]+)", str(query or ""), flags=re.IGNORECASE)\n    if not match:\n        return None\n    domain = match.group(1).casefold().removeprefix("www.")\n    # site:.pe / site:.com.pe are country-wide search scopes, not literal hosts.\n    if domain.startswith("."):\n        return None\n    return domain\n\n\ndef _country_scope_diversity_query(strong: str, seen_domains: set[str], *, round_index: int) -> str:\n    scope = ".pe" if round_index % 2 == 0 else ".com.pe"\n    domains = sorted({str(domain or "").strip().casefold().removeprefix("www.") for domain in seen_domains if str(domain or "").strip()})[:8]\n    exclusions = " ".join(f"-site:{domain}" for domain in domains)\n    return f'"{strong}" site:{scope} {exclusions}'.strip()\n\n\ndef _search_query_batches(identity: ProductIdentity, queries: list[str], per_query: int) -> list[list[str]]:\n'''
text = replace_once(text, old_helper, new_helper)

old_lane = '''            _emit_query_gain(on_query_event, lane="open_peru", query=query, signal_type=signal_type, metrics=metrics, before=before, after=set(seen), stop_reason=reason)\n            if len(rows) >= limit:\n                return rows\n\n    model = str(identity.model or identity.product_name or "").strip()\n'''
new_lane = '''            _emit_query_gain(on_query_event, lane="open_peru", query=query, signal_type=signal_type, metrics=metrics, before=before, after=set(seen), stop_reason=reason)\n            if len(rows) >= limit:\n                return rows\n\n    # Search engines often keep returning the same high-ranked Peru retailers.\n    # Use bounded negative-site expansion only after at least one valid retailer\n    # was found; this surfaces new domains without hardcoding an oracle/source list.\n    if rows and len(rows) < limit:\n        no_novelty_rounds = 0\n        for round_index in range(4):\n            before = set(seen)\n            seen_domains = {_host(url) for url in seen if _host(url)}\n            query = _country_scope_diversity_query(strong, seen_domains, round_index=round_index)\n            found, metrics = _search_with_metrics(identity, query, limit=per_query)\n            for raw in found:\n                url = str(raw or "").strip()\n                if not url.startswith(("http://", "https://")) or url in seen:\n                    continue\n                if not _is_peru_retail_candidate(url, strong, priority_domains=priority_domains):\n                    continue\n                seen.add(url)\n                rows.append(url)\n                if len(rows) >= limit:\n                    break\n            gained = bool(seen - before)\n            no_novelty_rounds = 0 if gained else no_novelty_rounds + 1\n            if len(rows) >= limit:\n                reason = "RETAIL_LIMIT_REACHED"\n            elif no_novelty_rounds >= 2:\n                reason = "DIVERSITY_NO_NOVELTY_STOP"\n            elif gained:\n                reason = "CONTINUE_NOVELTY"\n            else:\n                reason = "CONTINUE_NO_NOVELTY"\n            _emit_query_gain(\n                on_query_event,\n                lane="open_peru_diversity",\n                query=query,\n                signal_type="PERU_TLD_DIVERSITY",\n                metrics=metrics,\n                before=before,\n                after=set(seen),\n                stop_reason=reason,\n            )\n            if len(rows) >= limit or no_novelty_rounds >= 2:\n                break\n\n    model = str(identity.model or identity.product_name or "").strip()\n'''
text = replace_once(text, old_lane, new_lane)

TARGET.write_text(text, encoding="utf-8")
print("OPEN_PERU_DOMAIN_DIVERSITY_PATCH=APPLIED")
