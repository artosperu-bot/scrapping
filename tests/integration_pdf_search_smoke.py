from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from product_intelligence.batch import BatchItem, scrape_item
from product_intelligence.models import ProductIdentity
from product_intelligence.provider_runtime import provider_run_scope
from product_intelligence.source_strategy import SourceStrategy

PRODUCTS = [
    ProductIdentity(brand="JBL", model="Tune 530C", mpn="JBLT530CBLKAM"),
    ProductIdentity(brand="Logitech", model="MX Master 3S", mpn="910-006556"),
    ProductIdentity(brand="Apple", model="240W USB-C Charge Cable", mpn="A2794"),
    ProductIdentity(brand="Samsung", model="Galaxy S24 Ultra", mpn="SM-S928B"),
    ProductIdentity(brand="Lenovo", model="V15 G4 IRU"),
    ProductIdentity(brand="Ulefone", model="Armor 22"),
]

STRATEGY = SourceStrategy(web=True, pdf=True, ocr=False, mistral=False)
PROVIDER_SETTINGS = {
    "ocr_space_enabled": False,
    "mistral_enabled": False,
    "mistral_model": "mistral-small-latest",
    "request_timeout": 20,
}


def _source_types(rec) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ev in rec.evidence:
        counts[ev.source_type] = counts.get(ev.source_type, 0) + 1
    return dict(sorted(counts.items()))


def _score(rec) -> dict[str, object]:
    identity_ok = rec.identity.match_level in {"EXACT", "HIGH"}
    source_count = len(set(rec.sources or []))
    evidence_count = len(rec.evidence or [])
    attr_count = len(rec.specifications or {}) + len(rec.additional_attributes or {})
    manufacturer = (rec.fetch or {}).get("source_class") == "manufacturer" or any(
        "manufacturer" in str(note).lower() for note in (rec.technical_notes or [])
    )
    points = 0
    points += 25 if identity_ok else 10 if rec.identity.match_level == "MEDIUM" else 0
    points += min(20, source_count * 5)
    points += min(30, evidence_count)
    points += min(15, attr_count)
    points += 10 if manufacturer else 0
    return {
        "score_100": min(100, points),
        "identity_ok": identity_ok,
        "source_count": source_count,
        "evidence_count": evidence_count,
        "attribute_count": attr_count,
        "manufacturer_signal": manufacturer,
    }


def main() -> int:
    rows = []
    provider_events: list[dict] = []

    def audit(event: str, data: dict):
        provider_events.append({"event": event, **data})

    with provider_run_scope(PROVIDER_SETTINGS, audit=audit):
        for index, identity in enumerate(PRODUCTS, 1):
            logs: list[str] = []
            started = time.monotonic()
            try:
                with TemporaryDirectory(prefix=f"baseline-{index}-") as tmp:
                    rec = scrape_item(
                        BatchItem(row=index, sheet="BASELINE", identity=identity),
                        tmp,
                        template_plan=None,
                        log=logs.append,
                        source_strategy=STRATEGY,
                    )
                elapsed = round(time.monotonic() - started, 2)
                if rec is None:
                    row = {
                        "input_brand": identity.brand,
                        "input_model": identity.model,
                        "input_mpn": identity.mpn,
                        "status": "NO_VALIDATED_SOURCE",
                        "elapsed_seconds": elapsed,
                        "score_100": 0,
                        "logs": logs[-40:],
                    }
                else:
                    metrics = _score(rec)
                    safe = json.loads(rec.model_dump_json())
                    row = {
                        "input_brand": identity.brand,
                        "input_model": identity.model,
                        "input_mpn": identity.mpn,
                        "status": "SCRAPED",
                        "elapsed_seconds": elapsed,
                        **metrics,
                        "resolved_identity": safe["identity"],
                        "fetch": safe["fetch"],
                        "sources": safe["sources"],
                        "source_types": _source_types(rec),
                        "specifications": safe["specifications"],
                        "additional_attributes": safe["additional_attributes"],
                        "missing_fields": safe["missing_fields"],
                        "conflicts": safe["conflicts"],
                        "warnings": safe["warnings"],
                        "evidence_sample": safe["evidence"][:20],
                        "logs": logs[-60:],
                    }
            except Exception as exc:
                row = {
                    "input_brand": identity.brand,
                    "input_model": identity.model,
                    "input_mpn": identity.mpn,
                    "status": "ERROR",
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "score_100": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                    "logs": logs[-60:],
                }
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))

    forbidden = [
        event for event in provider_events
        if event.get("event") in {
            "OCR_PROVIDER_SELECTED",
            "OCR_SPACE_USED",
            "MISTRAL_DESCRIPTION_REQUESTED",
            "MISTRAL_DESCRIPTION_ACCEPTED",
        }
    ]
    summary = {
        "strategy": STRATEGY.as_options(),
        "products": len(rows),
        "scraped": sum(1 for row in rows if row["status"] == "SCRAPED"),
        "failed": sum(1 for row in rows if row["status"] != "SCRAPED"),
        "average_score_100": round(sum(float(row.get("score_100", 0)) for row in rows) / len(rows), 1),
        "provider_events": provider_events,
        "forbidden_provider_events": forbidden,
        "ocr_or_mistral_executed": bool(forbidden),
    }
    payload = {"summary": summary, "products": rows}
    Path("pdf-search-smoke.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("BASELINE_SUMMARY=" + json.dumps(summary, ensure_ascii=False))
    return 1 if forbidden else 0


if __name__ == "__main__":
    raise SystemExit(main())
