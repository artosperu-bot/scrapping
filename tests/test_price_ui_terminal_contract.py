from pathlib import Path


ROOT = Path(__file__).parents[1]
PRICE_DESKTOP = ROOT / "src" / "product_intelligence" / "price_desktop.py"


def _drain_body() -> str:
    source = PRICE_DESKTOP.read_text(encoding="utf-8")
    return source.split("    def _drain_price_events", 1)[1].split("\n    def ", 1)[0]


def test_price_event_pump_always_reschedules_after_event_processing_error():
    body = _drain_body()
    assert "finally:" in body
    assert "self.after(150, self._drain_price_events)" in body.split("finally:", 1)[1]
    assert "except Exception as exc:" in body


def test_batch_done_cannot_leave_price_ui_in_running_state():
    body = _drain_body()
    batch_done = body.split('elif kind == "batch_done":', 1)[1]
    assert "Finalización incompleta" in batch_done
    assert "self.price_progress_animation.set_error" in batch_done
    assert "self.price_progress_animation.set_completed" in batch_done
