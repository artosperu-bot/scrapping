from __future__ import annotations

import json
import os
import time
from pathlib import Path

from product_intelligence.identity_bootstrap import bootstrap_identity
from product_intelligence.models import ProductIdentity


# expected_brand is QA oracle only. It is never supplied to bootstrap_identity().
# The set intentionally mixes strong MPNs and descriptive model names across categories.
CASES = [
    ("Armor 22", ProductIdentity(product_name="Armor 22"), "Ulefone"),
    ("A2794", ProductIdentity(mpn="A2794"), "Apple"),
    ("SM-S928B", ProductIdentity(mpn="SM-S928B"), "Samsung"),
    ("910-006556", ProductIdentity(mpn="910-006556"), "Logitech"),
    ("JBLT530CBLKAM", ProductIdentity(mpn="JBLT530CBLKAM"), "JBL"),
    ("V15 G4 IRU", ProductIdentity(product_name="V15 G4 IRU"), "Lenovo"),
    ("SNV2S/1000G", ProductIdentity(mpn="SNV2S/1000G"), "Kingston"),
    ("Archer AX55", ProductIdentity(product_name="Archer AX55"), "TP-Link"),
    ("P2422H", ProductIdentity(model="P2422H"), "Dell"),
    ("HL-L2460DW", ProductIdentity(model="HL-L2460DW"), "Brother"),
    ("WH-1000XM5", ProductIdentity(model="WH-1000XM5"), "Sony"),
    ("L3250", ProductIdentity(model="L3250"), "Epson"),
    ("MF455dw", ProductIdentity(model="MF455dw"), "Canon"),
    ("2Z609A", ProductIdentity(mpn="2Z609A"), "HP"),
    ("G614JV", ProductIdentity(model="G614JV"), "ASUS"),
    ("A515-58M", ProductIdentity(model="A515-58M"), "Acer"),
    ("2312DRA50G", ProductIdentity(mpn="2312DRA50G"), "Xiaomi"),
    ("CT1000P3SSD8", ProductIdentity(mpn="CT1000P3SSD8"), "Crucial"),
    ("ST2000DM008", ProductIdentity(mpn="ST2000DM008"), "Seagate"),
    ("WDS100T3B0A", ProductIdentity(mpn="WDS100T3B0A"), "Western Digital"),
]


def _norm(value: str | None) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def _brand_matches(actual: str | None, expected: str) -> bool:
    a = _norm(actual)
    e = _norm(expected)
    aliases = {
        "tplink": {"tplink"},
        "western digital": {"westerndigital", "wd"},
    }
    accepted = aliases.get(expected.lower(), {e})
    return a in accepted


def _selected_cases():
    shard_count = max(1, int(os.getenv("IDENTITY_BENCH_SHARD_COUNT", "1")))
    shard_index = int(os.getenv("IDENTITY_BENCH_SHARD_INDEX", "0"))
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError("invalid shard index")
    return [case for idx, case in enumerate(CASES) if idx % shard_count == shard_index], shard_index, shard_count


def main() -> int:
    brands = {_norm(expected) for _, _, expected in CASES}
    assert len(CASES) == 20, f"benchmark must contain exactly 20 cases, got {len(CASES)}"
    assert len(brands) == 20, f"benchmark must contain 20 distinct brands, got {len(brands)}"

    selected, shard_index, shard_count = _selected_cases()
    rows = []
    failures = 0
    started_all = time.monotonic()

    for raw, identity, expected_brand in selected:
        started = time.monotonic()
        result = bootstrap_identity(identity.model_copy(deep=True), limit_per_query=18, timeout=8)
        elapsed = round(time.monotonic() - started, 2)
        passed = result.status == "RESOLVED" and _brand_matches(result.identity.brand, expected_brand)
        if not passed:
            failures += 1
        row = {
            "input": raw,
            "input_brand": identity.brand,
            "expected_brand": expected_brand,
            "resolved_brand": result.identity.brand,
            "resolved_model": result.identity.model,
            "status": result.status,
            "pass": passed,
            "confidence": round(float(result.confidence or 0.0), 3),
            "reason": result.reason,
            "queries": result.queries_executed,
            "candidate_urls": len(result.candidate_urls),
            "brand_scores": result.brand_scores,
            "brand_hosts": result.brand_hosts,
            "page_probes_attempted": result.page_probes_attempted,
            "page_probes_succeeded": result.page_probes_succeeded,
            "official_domain_hint": result.official_domain_hint,
            "hardcoded": result.hardcoded,
            "elapsed_seconds": elapsed,
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    summary = {
        "shard_index": shard_index,
        "shard_count": shard_count,
        "cases": len(rows),
        "passed": sum(1 for row in rows if row["pass"]),
        "failed": failures,
        "hardcoded_count": sum(1 for row in rows if row["hardcoded"]),
        "elapsed_seconds": round(time.monotonic() - started_all, 2),
    }
    payload = {"summary": summary, "products": rows}
    output = Path(f"identity-20-brand-shard-{shard_index}.json")
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("IDENTITY_20_BRAND_SUMMARY=" + json.dumps(summary, ensure_ascii=False))
    return 1 if failures or summary["hardcoded_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
