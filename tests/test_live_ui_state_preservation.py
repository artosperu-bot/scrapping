from types import SimpleNamespace

from product_intelligence.audit_events import AuditSink
from product_intelligence.live_ui_desktop import App


class FakeVar:
    def __init__(self): self.value = ""
    def set(self, value): self.value = str(value)


class FakeButton:
    def __init__(self): self.state = None
    def configure(self, **kwargs): self.state = kwargs.get("state", self.state)


def test_live_audit_bridge_records_excel_and_pdf_events_without_requiring_console():
    app = App.__new__(App)
    app.audit_sink = AuditSink()
    app._active_snapshots = {
        "run-excel": SimpleNamespace(run_id="run-excel", process_type="EXCEL")
    }

    app._record_live_audit("EXCEL", stage="SEARCH", status="PROGRESS", detail="Buscando fuentes")
    app._record_live_audit("PDF", run_id="pdf-review-0", product_id="ABC-1", stage="VALIDATE", status="FOUND", detail="manual.pdf")

    events = app.audit_sink.events()
    assert [(e.process_type, e.stage, e.status) for e in events] == [
        ("EXCEL", "SEARCH", "PROGRESS"),
        ("PDF", "VALIDATE", "FOUND"),
    ]


def test_pdf_live_state_is_preserved_per_product_when_switching_selection():
    row_a = SimpleNamespace(candidate=SimpleNamespace(url="https://docs.test/a.pdf"), inspection=object())
    row_b = SimpleNamespace(candidate=SimpleNamespace(url="https://docs.test/b.pdf"), inspection=object())
    app = App.__new__(App)
    app._pdf_review_candidates = {0: [], 1: []}
    app._pdf_review_inspections = {0: {}, 1: {}}
    app._pdf_review_selected = {0: set(), 1: set()}
    app._pdf_review_enforced = set()
    app._pdf_live_counts = {}
    current = {"index": 0}
    app._pdf_review_product_index = lambda: current["index"]
    app._pdf_review_refresh_tree = lambda: None

    app._apply_pdf_live_event(0, {"type": "validated", "row": row_a})
    current["index"] = 1
    app._apply_pdf_live_event(1, {"type": "validated", "row": row_b})
    current["index"] = 0

    assert [x.url for x in app._pdf_review_candidates[0]] == ["https://docs.test/a.pdf"]
    assert [x.url for x in app._pdf_review_candidates[1]] == ["https://docs.test/b.pdf"]


def test_error_recovery_helper_restores_control_and_allows_next_run():
    app = App.__new__(App)
    app._price_running = True
    app.price_selected_btn = FakeButton()
    app.price_all_btn = FakeButton()
    app.price_status = FakeVar()
    app._recover_live_controls("PRICE", "HTTP 403")

    assert app._price_running is False
    assert app.price_selected_btn.state == "normal"
    assert app.price_all_btn.state == "normal"
    assert "HTTP 403" in app.price_status.value
