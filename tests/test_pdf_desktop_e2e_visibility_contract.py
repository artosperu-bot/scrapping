from pathlib import Path


def test_pdf_review_workspace_exposes_pdf_output_folder():
    text = Path("src/product_intelligence/pdf_desktop_e2e.py").read_text(encoding="utf-8")
    final_shell = Path("src/product_intelligence/final_live_ui_desktop.py").read_text(encoding="utf-8")

    assert 'text="Abrir carpeta PDFs"' in text
    assert "def _pdf_review_open_folder(" in text
    assert "PdfDesktopE2EMixin" in final_shell


def test_live_pdf_review_forwards_worker_logs_to_global_desktop_log():
    text = Path("src/product_intelligence/pdf_desktop_e2e.py").read_text(encoding="utf-8")
    assert "[PDF REVIEW]" in text
    assert "def _apply_pdf_live_event(" in text
    assert "_emit_pdf_global(message)" in text
