from pathlib import Path


ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "product_intelligence"


def test_provider_buttons_are_enabled_and_real():
    source = (SRC / "provider_desktop.py").read_text(encoding="utf-8")
    assert "Probar conexión · pendiente" not in source
    assert 'text="Probar conexión"' in source
    assert "_test_provider_connection" in source
    assert "probe_ocr_space" in source
    assert "probe_mistral" in source


def test_provider_probe_runs_on_daemon_thread_and_returns_via_after():
    source = (SRC / "provider_desktop.py").read_text(encoding="utf-8")
    body = source.split("def _test_provider_connection", 1)[1].split("\n    def ", 1)[0]
    assert 'status_var.set("PROBANDO…")' in body
    assert "threading.Thread" in body
    assert "daemon=True" in body
    assert "self.after(" in source


def test_provider_probe_ui_supports_expected_states():
    source = (SRC / "provider_desktop.py").read_text(encoding="utf-8")
    for state in ("PROBANDO…", "CONECTADO", "RECHAZADO", "ERROR DE RED", "SIN CONFIGURAR"):
        assert state in source
