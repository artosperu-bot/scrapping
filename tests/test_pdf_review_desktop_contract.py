from pathlib import Path


def test_pdf_review_workspace_contract_is_present():
    text = Path("src/product_intelligence/pdf_review_shell.py").read_text(encoding="utf-8")

    required = [
        'text="Revisión PDF"',
        'text="Buscar PDFs"',
        'text="Usar / quitar"',
        'text="Confirmar selección"',
        'self._workspace_tabs["pdf_review"]',
        'self.pdf_review_tree = ttk.Treeview',
        'self.pdf_review_canvas = tk.Canvas',
        'def _pdf_review_search(',
        'def _pdf_review_inspect_selected(',
        'def _pdf_review_toggle_use(',
        'def _pdf_review_confirm(',
        'set_desktop_review_plan(',
    ]

    for token in required:
        assert token in text, token


def test_final_launcher_preserves_managed_entry_name_but_routes_to_pdf_review_shell():
    text = Path("run_desktop.py").read_text(encoding="utf-8")
    assert "product_intelligence.pdf_review_shell" in text
    assert "managed_main = pdf_review_main" in text
    assert "managed_main()" in text


def test_pdf_review_workspace_does_not_invoke_ocr_or_mistral_directly():
    text = Path("src/product_intelligence/pdf_review.py").read_text(encoding="utf-8").lower()
    forbidden_runtime_tokens = [
        "ocr_space_client",
        "remote_ocr_text",
        "paddleocr",
        "mistral_client",
        "remote_mistral",
        "mistralai",
    ]
    for token in forbidden_runtime_tokens:
        assert token not in text, token
