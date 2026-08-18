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


def _printer_identity():
    return ProductIdentity(
        brand="Example",
        model="Printer X1",
        mpn="PX1-100",
        confidence=.99,
        match_level="EXACT",
        identifiers_confirmed=["mpn"],
    )


def _record_for(identity, *fields):
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
        identity=identity,
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


def _record(*fields):
    return _record_for(_identity(), *fields)


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


def _index(logs, marker):
    return next(i for i, row in enumerate(logs) if marker in row)


def test_manual_exact_pdf_that_resolves_all_technical_fields_stops_before_web(monkeypatch, tmp_path):
    broad_web_calls = []
    targeted_web_calls = []
    logs = []

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
        log=logs.append,
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
    assert _index(logs, "SMART IDENTITY") < _index(logs, "SMART PLAN")
    assert _index(logs, "SMART PLAN") < _index(logs, "SMART SOURCE")
    assert _index(logs, "SMART SOURCE") < _index(logs, "SMART FIELDS")
    assert _index(logs, "SMART FIELDS") < _index(logs, "SMART FINAL")


def test_partial_pdf_sends_only_remaining_field_to_targeted_web(monkeypatch, tmp_path):
    broad_web_calls = []
    targeted_fields = []
    logs = []

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
        log=logs.append,
        source_strategy=SourceStrategy(web=True, pdf=True, ocr=False, mistral=False),
    )

    assert result is not None
    assert broad_web_calls == []
    assert targeted_fields == [("driver_size",)]
    audit = result.evidence_graph["smart_orchestrator"]
    assert audit["resolved_fields"] == ["battery_capacity"]
    assert audit["missing_fields"] == ["driver_size"]
    assert any("SMART NEXT_SOURCE: WEB_STRUCTURED" in row and "driver_size" in row for row in logs)
    assert any("SMART QUERY:" in row and "engine=WEB_STRUCTURED" in row for row in logs)


def test_batch_passes_classification_and_source_kind_to_real_missing_field_search(monkeypatch, tmp_path):
    calls = []
    printer = _printer_identity()
    item = batch.BatchItem(
        row=2,
        sheet="Products",
        identity=printer,
        source_url="https://manufacturer.test/printer-spec.pdf",
    )

    monkeypatch.setattr(batch, "search_web", lambda *a, **k: [])
    monkeypatch.setattr(batch, "discover_product_documents", lambda *a, **k: [])
    monkeypatch.setattr(
        batch,
        "process_pdf_document",
        lambda *a, **k: _record_for(printer, ("battery_capacity", "5000 mAh")),
    )

    def search_fields(_identity, fields, **kwargs):
        calls.append((tuple(fields), dict(kwargs)))
        return []

    monkeypatch.setattr(batch, "search_web_for_fields", search_fields)

    result = batch.scrape_item(
        item,
        str(tmp_path),
        template_plan=_plan("battery_capacity", "warranty"),
        source_strategy=SourceStrategy(web=True, pdf=True, ocr=False, mistral=False),
    )

    assert result is not None
    assert calls
    fields, kwargs = calls[0]
    assert fields == ("warranty",)
    assert kwargs["source_kind"] == "MANUFACTURER_SUPPORT"
    assert kwargs["category"] == "PRINTER"
    audit = result.evidence_graph["smart_orchestrator"]
    assert audit["category"] == "PRINTER"


def test_pdf_zero_with_exact_identity_continues_to_targeted_web(monkeypatch, tmp_path):
    targeted_calls = []
    logs = []
    candidate = type(
        "Candidate",
        (),
        {"url": "https://manufacturer.test/model-x", "likely_official": True, "score": 1.0},
    )()

    monkeypatch.setattr(batch, "search_web", lambda *a, **k: (_ for _ in ()).throw(AssertionError("broad WEB must not run before PDF")))
    monkeypatch.setattr(batch, "discover_product_documents", lambda *a, **k: [])

    def search_fields(_identity, fields, **kwargs):
        targeted_calls.append((tuple(fields), dict(kwargs)))
        return [candidate]

    monkeypatch.setattr(batch, "search_web_for_fields", search_fields)

    class FakePipeline:
        def process_url(self, *args, **kwargs):
            return _record(("driver_size", "40 mm"))

    monkeypatch.setattr(batch, "ProductPipeline", FakePipeline)

    item = batch.BatchItem(row=2, sheet="Products", identity=_identity())
    result = batch.scrape_item(
        item,
        str(tmp_path),
        template_plan=_plan("driver_size"),
        log=logs.append,
        source_strategy=SourceStrategy(web=True, pdf=True, ocr=False, mistral=False),
    )

    assert result is not None
    assert targeted_calls
    assert targeted_calls[0][0] == ("driver_size",)
    assert targeted_calls[0][1]["source_kind"] == "MANUFACTURER"
    assert result.evidence_graph["smart_orchestrator"]["resolved_fields"] == ["driver_size"]
    assert any("SMART NEXT_SOURCE: WEB_STRUCTURED" in row for row in logs)
