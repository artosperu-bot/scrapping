from types import SimpleNamespace

from product_intelligence import batch
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord
from product_intelligence.source_strategy import SourceStrategy


def _identity():
    return ProductIdentity(
        brand="Example",
        model="Example Model Wireless",
        mpn="EX-100-WL",
        confidence=.99,
        match_level="EXACT",
        identifiers_confirmed=["mpn"],
    )


def _record(*fields):
    evidence = [
        Evidence(
            attribute=field,
            raw_value=value,
            normalized_value=value,
            source_url="https://manufacturer.test/spec.pdf",
            source_type="official_pdf",
            extraction_method="pdf_native",
            match_level="EXACT",
            confidence=.96,
            identity_status="EXACT",
            authority="manufacturer",
            policy_allowed=True,
            document_relationship="EXACT_MODEL",
            document_scope="MODEL",
        )
        for field, value in fields
    ]
    return ProductRecord(
        identity=_identity(),
        evidence=evidence,
        sources=["https://manufacturer.test/spec.pdf"],
        fetch={
            "source_class": "manufacturer",
            "final_url": "https://manufacturer.test/spec.pdf",
            "source_decision": {
                "page_type": "DOCUMENT",
                "identity": "EXACT",
                "authority": "manufacturer",
                "material_allowed": True,
            },
        },
    )


def _item():
    return batch.BatchItem(
        row=2,
        sheet="Products",
        identity=_identity(),
        source_url="https://manufacturer.test/spec.pdf",
    )


def _plan(*fields):
    return {
        "scrape_semantics": list(fields),
        "media_slots": 0,
        "summary": {"scrape_targets": len(fields)},
    }


def test_manual_exact_pdf_that_resolves_all_technical_fields_stops_before_web(monkeypatch, tmp_path):
    broad_web_calls = []
    targeted_web_calls = []

    monkeypatch.setattr(batch, "search_web", lambda *a, **k: broad_web_calls.append((a, k)) or [])
    monkeypatch.setattr(batch, "search_web_for_fields", lambda *a, **k: targeted_web_calls.append((a, k)) or [])
    monkeypatch.setattr(batch, "discover_product_documents", lambda *a, **k: [])
    monkeypatch.setattr(
        batch,
        "process_pdf_document",
        lambda *a, **k: _record(("battery_capacity", "5000 mAh"), ("driver_size", "40 mm")),
    )

    result = batch.scrape_item(
        _item(),
        str(tmp_path),
        template_plan=_plan("battery_capacity", "driver_size"),
        source_strategy=SourceStrategy(web=True, pdf=True, ocr=False, mistral=False),
    )

    assert result is not None
    assert broad_web_calls == []
    assert targeted_web_calls == []
    audit = result.evidence_graph["smart_orchestrator"]
    assert audit["resolved_fields"] == ["battery_capacity", "driver_size"]
    assert audit["missing_fields"] == []
    assert audit["early_stop"] is True
    assert audit["stop_reason"] == "SUFFICIENT_FIELD_COVERAGE"


def test_partial_pdf_sends_only_remaining_field_to_targeted_web(monkeypatch, tmp_path):
    broad_web_calls = []
    targeted_fields = []

    monkeypatch.setattr(batch, "search_web", lambda *a, **k: broad_web_calls.append((a, k)) or [])

    def search_fields(_identity, fields, **kwargs):
        targeted_fields.append(tuple(fields))
        return []

    monkeypatch.setattr(batch, "search_web_for_fields", search_fields)
    monkeypatch.setattr(batch, "discover_product_documents", lambda *a, **k: [])
    monkeypatch.setattr(batch, "process_pdf_document", lambda *a, **k: _record(("battery_capacity", "5000 mAh")))

    result = batch.scrape_item(
        _item(),
        str(tmp_path),
        template_plan=_plan("battery_capacity", "driver_size"),
        source_strategy=SourceStrategy(web=True, pdf=True, ocr=False, mistral=False),
    )

    assert result is not None
    assert broad_web_calls == []
    assert targeted_fields == [("driver_size",)]
    audit = result.evidence_graph["smart_orchestrator"]
    assert audit["resolved_fields"] == ["battery_capacity"]
    assert audit["missing_fields"] == ["driver_size"]
