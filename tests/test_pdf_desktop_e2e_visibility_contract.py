from pathlib import Path


def test_pdf_review_workspace_exposes_pdf_output_folder():
    text = Path("src/product_intelligence/pdf_review_shell.py").read_text(encoding="utf-8")
    assert 'text="Abrir carpeta PDFs"' in text
    assert "def _pdf_review_open_folder(" in text


def test_live_pdf_review_forwards_worker_logs_to_global_desktop_log():
    text = Path("src/product_intelligence/live_ui_desktop.py").read_text(encoding="utf-8")
    assert "[PDF REVIEW]" in text
    assert "self.emit(" in text[text.index("def _pdf_review_search"):]
