from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from product_intelligence import discovery
from product_intelligence.models import ProductIdentity
from product_intelligence.price_identity_resolution import resolve_price_identity
from product_intelligence.price_peru_coverage import _general_retail_query_specs

INPUT = ProductIdentity(mpn="SA400S37/960G")
# Audit labels only; never inserted into a search query.
TARGETS = {
    "Memory Kings": "memorykings.pe",
    "Gidat": "gidat.pe",
    "Computer House": "computerhouse.pe",
    "UnikStore": "unikstoreperu.com",
    "Sercoplus": "sercoplus.com",
    "EAC": "eac.com.pe",
}
PROVIDERS = {
    "ddg": discovery._search_ddg,
    "bing_html": discovery._search_bing,
    "bing_rss": discovery._search_bing_rss,
    "brave": discovery._search_brave,
    "mojeek": discovery._search_mojeek,
    "yahoo": discovery._search_yahoo,
}


def host(url: str) -> str:
    return (urlparse(url).hostname or "").casefold().removeprefix("www.")


def matches(url: str, domain: str) -> bool:
    h = host(url)
    return h == domain or h.endswith("." + domain)


def main() -> int:
    resolution = resolve_price_identity(INPUT, timeout=8, limit_per_query=18)
    identity = resolution.identity
    specs = [
        (query, signal)
        for query, signal in _general_retail_query_specs(identity)
        if signal == "VERIFIED_BRAND_MPN_PERU_TLD_SCOPE"
    ]
    report = {
        "input": INPUT.model_dump(),
        "resolution": {
            "status": resolution.status,
            "evidence_backed": resolution.evidence_backed,
            "brand": identity.brand,
            "mpn": identity.mpn,
        },
        "queries": [q for q, _ in specs],
        "providers": {},
        "targets": {},
    }
    if resolution.status != "RESOLVED" or not resolution.evidence_backed or len(specs) != 2:
        report["error"] = "IDENTITY_OR_QUERY_CONTRACT_NOT_READY"
        Path("p7_provider_matrix.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2

    for provider_name, fn in PROVIDERS.items():
        provider_rows = []
        for query, _signal in specs:
            rows = fn(query, 8)
            provider_rows.append({
                "query": query,
                "count": len(rows),
                "rows": [
                    {"url": str(url), "title": str(title), "snippet": str(snippet)[:500]}
                    for url, title, snippet in rows
                ],
            })
        report["providers"][provider_name] = provider_rows

    for label, domain in TARGETS.items():
        hits = []
        for provider_name, query_rows in report["providers"].items():
            for row in query_rows:
                for item in row["rows"]:
                    if matches(item["url"], domain):
                        hits.append({"provider": provider_name, "query": row["query"], **item})
        report["targets"][label] = {
            "domain": domain,
            "provider_hit": bool(hits),
            "hits": hits,
        }

    Path("p7_provider_matrix.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("P7_PROVIDER_MATRIX=", json.dumps({k: {"hit": v["provider_hit"], "providers": sorted({h["provider"] for h in v["hits"]})} for k, v in report["targets"].items()}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
