from pathlib import Path


ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "product_intelligence"


def test_scraping_desktop_exposes_per_run_source_controls_and_presets():
    source = (SRC / "pdf_desktop.py").read_text(encoding="utf-8")
    for label in (
        "Fuentes de esta ejecución",
        "Web / HTML",
        "PDF",
        "OCR.space",
        "Mistral",
        "Automático",
        "Solo Web",
        "Solo PDF",
        "Web + PDF",
    ):
        assert label in source
    assert "source_web_enabled" in source
    assert "ocr_run_enabled" in source
    assert "mistral_run_enabled" in source


def test_execution_snapshot_freezes_source_strategy_and_batch_receives_it():
    source = (SRC / "pdf_desktop.py").read_text(encoding="utf-8")
    assert '"source_web_enabled"' in source
    assert '"source_pdf_enabled"' in source
    assert '"ocr_space_enabled"' in source
    assert '"mistral_enabled"' in source
    assert "SourceStrategy(" in source
    assert "source_strategy=strategy" in source
    assert "SOURCE_STRATEGY_REQUIRES_WEB_OR_PDF" in source


def test_pdf_off_forces_ocr_off_and_pdf_scope_uses_snapshot_value():
    source = (SRC / "pdf_desktop.py").read_text(encoding="utf-8")
    assert "def _sync_source_dependencies" in source
    assert "self.ocr_run_enabled.set(False)" in source
    assert 'bool(job.option("source_pdf_enabled", True))' in source
    assert 'bool(job.option("ocr_space_enabled", False))' in source
