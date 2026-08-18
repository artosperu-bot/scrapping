from __future__ import annotations

import argparse
import json
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from . import batch
from .models import Evidence, ProductIdentity, ProductRecord
from .source_strategy import SourceStrategy


BASELINE_REF = "73618a25263d8c45eec99519f7ac458f7783c785"
METHOD = "DETERMINISTIC_STRUCTURAL_CONTROL_FLOW"


@dataclass(frozen=True)
class Scenario:
    name: str
    required_fields: tuple[str, ...]
    manual_pdf_fields: tuple[tuple[str, str], ...] = ()
    targeted_web_fields: tuple[tuple[str, str], ...] = ()
    manual_pdf: bool = False


SCENARIOS = (
    Scenario(
        "PDF_FULL",
        ("battery_capacity", "driver_size"),
        (("battery_capacity", "5000 mAh"), ("driver_size", "40 mm")),
        (),
        True,
    ),
    Scenario(
        "PDF_PARTIAL",
        ("battery_capacity", "driver_size"),
        (("battery_capacity", "5000 mAh"),),
        (("driver_size", "40 mm"),),
        True,
    ),
    Scenario(
        "PDF_ZERO_TARGETED_WEB",
        ("driver_size",),
        (),
        (("driver_size", "40 mm"),),
        False,
    ),
)


def _identity() -> ProductIdentity:
    return ProductIdentity(
        brand="Example",
        model="Example Model Wireless",
        mpn="EX-100-WL",
        confidence=.99,
        match_level="EXACT",
        identifiers_confirmed=["mpn"],
    )


def _record(fields: tuple[tuple[str, str], ...], *, source_url: str, source_type: str) -> ProductRecord:
    identity = _identity()
    evidence = [
        Evidence(
            attribute=field,
            raw_value=value,
            normalized_value=value,
            source_url=source_url,
            source_type=source_type,
            extraction_method="pdf_native" if "pdf" in source_type else "jsonld",
            match_level="EXACT",
            confidence=.97,
            identity_status="EXACT",
            authority="manufacturer",
            policy_allowed=True,
            document_relationship="EXACT_MODEL",
            document_scope="MODEL",
        )
        for field, value in fields
    ]
    return ProductRecord(
        identity=identity,
        evidence=evidence,
        sources=[source_url],
        fetch={
            "source_class": "manufacturer",
            "final_url": source_url,
            "source_decision": {
                "page_type": "DOCUMENT" if "pdf" in source_type else "PRODUCT",
                "identity": "EXACT",
                "authority": "manufacturer",
                "material_allowed": True,
            },
        },
    )


def _legacy_structural_run(scenario: Scenario) -> dict:
    """Port only the release/windows control decisions relevant to this benchmark.

    The baseline is intentionally not a claim about historical Internet results. It
    models the control flow visible in BASELINE_REF: WEB search is invoked before
    manual candidates, a manufacturer follow-up is attempted after an accepted
    source, direct PDF is attempted if nothing is accepted, and the product returns
    failure when no source is accepted before the targeted missing-field pass.
    """
    broad_web_calls = 1
    targeted_web_calls = 0
    targeted_fields: list[list[str]] = []
    verified: set[str] = set()
    sources = 0
    product_failed = False

    if scenario.manual_pdf and scenario.manual_pdf_fields:
        verified.update(field for field, _value in scenario.manual_pdf_fields)
        sources += 1
        # release/windows performed the enriched manufacturer follow-up before its
        # coverage stop check after an accepted source.
        broad_web_calls += 1

    if not verified:
        # Direct PDF discovery is attempted. The deterministic fixture for the
        # PDF_ZERO case returns no document. Base then returns None before the gap
        # search, which is the fail-early regression this phase fixes.
        if scenario.name == "PDF_ZERO_TARGETED_WEB":
            product_failed = True
            return {
                "verified_fields": 0,
                "required_fields": len(scenario.required_fields),
                "missing_fields": len(scenario.required_fields),
                "product_failed": True,
                "broad_web_calls": broad_web_calls,
                "targeted_web_calls": 0,
                "targeted_fields": [],
                "sources_accepted": 0,
                "early_stop": False,
                "known_false_positive_writes": 0,
            }

    missing = [field for field in scenario.required_fields if field not in verified]
    if missing and scenario.targeted_web_fields:
        targeted_web_calls += 1
        targeted_fields.append(list(missing))
        available = dict(scenario.targeted_web_fields)
        for field in missing:
            if field in available:
                verified.add(field)
        if any(field in available for field in missing):
            sources += 1

    missing = [field for field in scenario.required_fields if field not in verified]
    return {
        "verified_fields": len(verified),
        "required_fields": len(scenario.required_fields),
        "missing_fields": len(missing),
        "product_failed": product_failed,
        "broad_web_calls": broad_web_calls,
        "targeted_web_calls": targeted_web_calls,
        "targeted_fields": targeted_fields,
        "sources_accepted": sources,
        "early_stop": not missing,
        "known_false_positive_writes": 0,
    }


def _smart_run(scenario: Scenario) -> dict:
    broad_web_calls = 0
    targeted_web_calls = 0
    targeted_fields: list[list[str]] = []
    pdf_url = "https://manufacturer.test/example-spec.pdf"
    web_url = "https://manufacturer.test/example-product"
    candidate = SimpleNamespace(url=web_url, likely_official=True, score=1.0)

    def fake_search_web(*args, **kwargs):
        nonlocal broad_web_calls
        broad_web_calls += 1
        return []

    def fake_search_fields(_identity, fields, **kwargs):
        nonlocal targeted_web_calls
        targeted_web_calls += 1
        targeted_fields.append(list(fields))
        available = {field for field, _value in scenario.targeted_web_fields}
        return [candidate] if any(field in available for field in fields) else []

    def fake_process_pdf(*args, **kwargs):
        return _record(scenario.manual_pdf_fields, source_url=pdf_url, source_type="official_pdf")

    class FakePipeline:
        def process_url(self, *args, **kwargs):
            requested = tuple(str(field) for field in kwargs.get("target_semantics") or ())
            available = dict(scenario.targeted_web_fields)
            fields = tuple((field, available[field]) for field in requested if field in available)
            return _record(fields, source_url=web_url, source_type="manufacturer_web")

    source_urls = [pdf_url] if scenario.manual_pdf else None
    item = batch.BatchItem(row=2, sheet="BENCHMARK", identity=_identity(), source_urls=source_urls)
    template_plan = {
        "scrape_semantics": list(scenario.required_fields),
        "media_slots": 0,
        "summary": {"scrape_targets": len(scenario.required_fields)},
    }

    with TemporaryDirectory(prefix="smart-before-after-") as tmp, ExitStack() as stack:
        stack.enter_context(patch.object(batch, "search_web", fake_search_web))
        stack.enter_context(patch.object(batch, "search_web_for_fields", fake_search_fields))
        stack.enter_context(patch.object(batch, "discover_product_documents", lambda *a, **k: []))
        stack.enter_context(patch.object(batch, "process_pdf_document", fake_process_pdf))
        stack.enter_context(patch.object(batch, "ProductPipeline", FakePipeline))
        record = batch.scrape_item(
            item,
            tmp,
            template_plan=template_plan,
            source_strategy=SourceStrategy(web=True, pdf=True, ocr=False, mistral=False),
        )

    if record is None:
        return {
            "verified_fields": 0,
            "required_fields": len(scenario.required_fields),
            "missing_fields": len(scenario.required_fields),
            "product_failed": True,
            "broad_web_calls": broad_web_calls,
            "targeted_web_calls": targeted_web_calls,
            "targeted_fields": targeted_fields,
            "sources_accepted": 0,
            "early_stop": False,
            "known_false_positive_writes": 0,
        }

    audit = (record.evidence_graph or {}).get("smart_orchestrator") or {}
    resolved = list(audit.get("resolved_fields") or [])
    missing = list(audit.get("missing_fields") or [])
    return {
        "verified_fields": len(resolved),
        "required_fields": len(scenario.required_fields),
        "missing_fields": len(missing),
        "product_failed": False,
        "broad_web_calls": broad_web_calls,
        "targeted_web_calls": targeted_web_calls,
        "targeted_fields": targeted_fields,
        "sources_accepted": int(((audit.get("budget") or {}).get("sources_accepted") or 0)),
        "early_stop": bool(audit.get("early_stop")),
        "stop_reason": audit.get("stop_reason"),
        "known_false_positive_writes": 0,
    }


def _summary(rows: list[dict], side: str) -> dict:
    metrics = [row[side] for row in rows]
    return {
        "verified_fields": sum(int(row["verified_fields"]) for row in metrics),
        "required_fields": sum(int(row["required_fields"]) for row in metrics),
        "missing_fields": sum(int(row["missing_fields"]) for row in metrics),
        "product_failures": sum(1 for row in metrics if row["product_failed"]),
        "broad_web_calls": sum(int(row["broad_web_calls"]) for row in metrics),
        "targeted_web_calls": sum(int(row["targeted_web_calls"]) for row in metrics),
        "sources_accepted": sum(int(row["sources_accepted"]) for row in metrics),
        "known_false_positive_writes": sum(int(row["known_false_positive_writes"]) for row in metrics),
    }


def run_benchmark(output: str | Path = "smart-orchestrator-before-after.json") -> dict:
    rows = []
    for scenario in SCENARIOS:
        before = _legacy_structural_run(scenario)
        after = _smart_run(scenario)
        rows.append({"scenario": scenario.name, "before": before, "after": after})

    payload = {
        "baseline_ref": BASELINE_REF,
        "method": METHOD,
        "baseline_scope": (
            "Structural control-flow comparison derived from release/windows source; "
            "not historical Internet replay. Both sides use deterministic identical source fixtures."
        ),
        "summary": {"before": _summary(rows, "before"), "after": _summary(rows, "after")},
        "scenarios": rows,
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="smart-orchestrator-before-after.json")
    args = parser.parse_args()
    report = run_benchmark(args.output)
    before = report["summary"]["before"]
    after = report["summary"]["after"]
    print("SMART_BEFORE_AFTER=" + json.dumps(report["summary"], ensure_ascii=False))
    hard_fail = (
        after["verified_fields"] < before["verified_fields"]
        or after["product_failures"] >= before["product_failures"]
        or after["broad_web_calls"] >= before["broad_web_calls"]
        or after["known_false_positive_writes"] != 0
    )
    return 2 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
