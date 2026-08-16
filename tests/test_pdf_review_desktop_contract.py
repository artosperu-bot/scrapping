from pathlib import Path


def test_pdf_review_workspace_contract_is_present():
    text = Path("src/product_intelligence/pdf_desktop.py").read_text(encoding="utf-8")

    required = [
        'text="Revisión PDF"',
        'text="Buscar PDFs"',
        'text="Usar / quitar"',
        'text="Confirmar selección"',
        'self._workspace_tabs["pdf_review"]',
        'self.pdf_review_tree = ttk.Treeview',
        'self.pdf_review_preview',
        'def _pdf_review_search(',
        'def _pdf_review_inspect_selected(',
        'def _pdf_review_toggle_use(',
        'def _pdf_review_confirm(',
        'reviewed_pdf_urls_by_index=',
        'pdf_review_flags=',
    ]

    for token in required:
        assert token in text, token


def test_pdf_review_workspace_does_not_invoke_ocr_or_mistral_directly():
    text = Path("src/product_intelligence/pdf_review.py").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "ocr_space" not in lowered
    assert "mistral" not in lowered
