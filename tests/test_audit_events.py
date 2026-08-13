from product_intelligence.audit_events import AuditEvent, AuditSink, filter_events


def test_audit_sink_keeps_processes_separate():
    sink = AuditSink()
    sink.emit(AuditEvent.create("EXCEL-1", "EXCEL", status="DONE", product_id="MPN-1", detail="excel done"))
    sink.emit(AuditEvent.create("MEDIA-1", "MEDIA", status="REJECTED", product_id="MPN-1", detail="wrong image"))
    sink.emit(AuditEvent.create("PRICE-1", "PRICE", status="ERROR", product_id="GTIN-2", detail="price error"))

    assert [e.run_id for e in filter_events(sink.events(), process_type="EXCEL")] == ["EXCEL-1"]
    assert [e.run_id for e in filter_events(sink.events(), status="REJECTED")] == ["MEDIA-1"]
    assert [e.run_id for e in filter_events(sink.events(), status="ERROR")] == ["PRICE-1"]
    assert [e.run_id for e in filter_events(sink.events(), query="GTIN-2")] == ["PRICE-1"]
