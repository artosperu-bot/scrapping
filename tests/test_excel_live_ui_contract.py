from product_intelligence.live_ui_desktop import App


class FakeVar:
    def __init__(self): self.value = ""
    def set(self, value): self.value = str(value)


def _app():
    app = App.__new__(App)
    app._excel_live_counts = {
        "sources": 0,
        "validated": 0,
        "fields_resolved": 0,
        "fields_pending": 0,
        "fields_conflicted": 0,
        "queries": 0,
        "pdf_found": 0,
        "pdf_used": 0,
    }
    app._excel_live_sources = set()
    app.excel_live_counters = FakeVar()
    return app


def test_excel_live_log_tracks_real_sources_validation_and_semantic_counts():
    app = _app()
    app._observe_excel_log("  probando: https://shop.test/p")
    app._observe_excel_log("  fuente validada: manufacturer / EXACT")
    app._observe_excel_log("  cobertura actual: 8/10 semánticas; pendientes=2")
    assert app._excel_live_counts["sources"] == 1
    assert app._excel_live_counts["validated"] == 1
    assert app._excel_live_counts["fields_resolved"] == 8
    assert app._excel_live_counts["fields_pending"] == 2
    assert "Fuentes: 1" in app.excel_live_counters.value
    assert "Validadas: 1" in app.excel_live_counters.value
    assert "Campos: 8 resueltos / 2 pendientes" in app.excel_live_counters.value


def test_excel_live_log_tracks_pdf_without_inventing_ocr_or_mistral():
    app = _app()
    app._observe_excel_log("  PDF CANDIDATOS: 3")
    app._observe_excel_log("  PDF VALIDADO: https://docs.test/manual.pdf")
    assert app._excel_live_counts["pdf_found"] == 3
    assert app._excel_live_counts["pdf_used"] == 1
    text = app.excel_live_counters.value
    assert "PDF: 3 encontrados / 1 usados" in text
    assert "OCR" not in text
    assert "Mistral" not in text


def test_excel_product_marker_sets_identity_stage_before_search_stage():
    app = _app()
    assert app._excel_stage_from_log("[2/5] ABC-123") == "IDENTITY"
    assert app._excel_stage_from_log("  probando: https://example.test") == "SEARCH"
    assert app._excel_stage_from_log("  fuente validada: manufacturer / EXACT") == "EXTRACT"
    assert app._excel_stage_from_log("  cobertura actual: 7/9 semánticas; pendientes=2") == "SEMANTIC RESOLUTION"


def test_excel_live_ui_understands_smart_orchestrator_stages_and_counters():
    app = _app()
    app._observe_excel_log("  SMART PLAN: requeridos=10 pendientes=4 next=PDF")
    app._observe_excel_log("  SMART QUERY: used=3 limit=8 engine=WEB_STRUCTURED")
    app._observe_excel_log("  SMART FIELDS: verificados=7 faltantes=2 conflictos=1")
    app._observe_excel_log("  SMART FINAL: verified=7/10 missing=2 conflicts=1 stop=NO")

    assert app._excel_live_counts["queries"] == 3
    assert app._excel_live_counts["fields_resolved"] == 7
    assert app._excel_live_counts["fields_pending"] == 2
    assert app._excel_live_counts["fields_conflicted"] == 1
    assert "Consultas: 3/8" in app.excel_live_counters.value
    assert "Conflictos: 1" in app.excel_live_counters.value
    assert app._excel_stage_from_log("  SMART IDENTITY: JBL / Endurance Run 3 Wireless") == "IDENTITY"
    assert app._excel_stage_from_log("  SMART PLAN: requeridos=10 pendientes=4 next=PDF") == "PLAN"
    assert app._excel_stage_from_log("  SMART SOURCE: PDF kind=OFFICIAL_PDF fields=driver_size") == "SOURCE"
    assert app._excel_stage_from_log("  SMART QUERY: used=3 limit=8 engine=WEB_STRUCTURED") == "QUERY"
    assert app._excel_stage_from_log("  SMART FIELDS: verificados=7 faltantes=2 conflictos=1") == "SEMANTIC RESOLUTION"
    assert app._excel_stage_from_log("  SMART NEXT_SOURCE: WEB_STRUCTURED kind=MANUFACTURER fields=warranty") == "NEXT SOURCE"
    assert app._excel_stage_from_log("  SMART FINAL: verified=7/10 missing=2 conflicts=1 stop=NO") == "FINAL"
