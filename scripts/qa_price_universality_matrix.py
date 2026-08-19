from __future__ import annotations

import json
from pathlib import Path

from product_intelligence.models import ProductIdentity
from product_intelligence.price_queries import build_price_query_plan


CASES = (
    ("computing", "ACME-COMP/960G", "Acme Computing", "Compute 960"),
    ("audio", "ACME-AUDIO/350", "Acme Audio", "Wireless 350"),
    ("smartphone", "ACME-PHONE/25", "Acme Mobile", "Rugged 25"),
    ("appliance_tool", "ACME-TOOL/500", "Acme Home", "Tool 500"),
    ("non_electronic", "ACME-OFFICE/01", "Acme Office", "Office 01"),
)

VALID_UPC = "036000291452"
VALID_EAN = "4006381333931"


def _identity(mode: str, *, mpn: str, brand: str, model: str) -> ProductIdentity:
    if mode == "mpn_only":
        return ProductIdentity(mpn=mpn)
    if mode == "upc_only":
        return ProductIdentity(upc=VALID_UPC)
    if mode == "ean_only":
        return ProductIdentity(ean=VALID_EAN)
    if mode == "brand_model":
        return ProductIdentity(brand=brand, model=model)
    raise ValueError(mode)


def build_matrix() -> dict:
    rows = []
    for category, mpn, brand, model in CASES:
        for mode in ("mpn_only", "upc_only", "ean_only", "brand_model"):
            identity = _identity(mode, mpn=mpn, brand=brand, model=model)
            plan = build_price_query_plan(identity, limit=12)
            queries = [row.query for row in plan]
            signal_types = [row.signal_type for row in plan]
            unique = len(queries) == len({query.casefold() for query in queries})
            expected = {
                "mpn_only": any(signal.startswith("MPN_") for signal in signal_types),
                "upc_only": "UPC" in signal_types,
                "ean_only": "EAN" in signal_types,
                "brand_model": "BRAND_MODEL" in signal_types,
            }[mode]
            passed = bool(plan) and len(plan) <= 12 and unique and expected
            rows.append(
                {
                    "category": category,
                    "mode": mode,
                    "input": identity.model_dump(),
                    "query_count": len(plan),
                    "signal_types": signal_types,
                    "queries": queries,
                    "bounded": len(plan) <= 12,
                    "casefold_unique": unique,
                    "expected_signal_present": expected,
                    "pass": passed,
                }
            )
    passed = sum(1 for row in rows if row["pass"])
    return {
        "cases": len(CASES),
        "modes": 4,
        "rows": rows,
        "summary": {"passed": passed, "total": len(rows), "green": passed == len(rows)},
    }


def main() -> int:
    report = build_matrix()
    output = Path("universality_matrix.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("UNIVERSALITY_MATRIX=", json.dumps(report["summary"], sort_keys=True))
    if not report["summary"]["green"]:
        raise SystemExit("universality matrix failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
