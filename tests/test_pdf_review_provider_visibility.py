from pathlib import Path


def test_pdf_review_explains_post_selection_ocr_and_mistral_roles():
    source = Path("src/product_intelligence/pdf_review_shell.py").read_text(encoding="utf-8")

    assert "Procesamiento después de confirmar" in source
    assert "OCR.space" in source
    assert "solo si falta texto nativo" in source
    assert "Mistral" in source
    assert "descripción" in source.lower()
    assert "no lee ni valida el PDF" in source
    assert "_pdf_review_refresh_provider_status" in source


def test_pdf_review_provider_status_reads_existing_provider_controls_not_new_secrets():
    source = Path("src/product_intelligence/pdf_review_shell.py").read_text(encoding="utf-8")

    assert "self.ocr_enabled" in source
    assert "self.mistral_enabled" in source
    assert "self.ocr_status" in source
    assert "self.mistral_status" in source
    assert "save_value(" not in source
    assert "load_value(" not in source
