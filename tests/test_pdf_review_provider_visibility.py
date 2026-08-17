from pathlib import Path


def _provider_visibility_source() -> str:
    return Path("src/product_intelligence/pdf_review_provider_ui.py").read_text(encoding="utf-8")


def test_pdf_review_explains_post_selection_ocr_and_mistral_roles():
    source = _provider_visibility_source()

    assert "Procesamiento después de confirmar" in source
    assert "OCR.space" in source
    assert "solo si falta texto nativo" in source
    assert "Mistral" in source
    assert "descripción" in source.lower()
    assert "no lee ni valida el PDF" in source
    assert "_pdf_review_refresh_provider_status" in source


def test_pdf_review_provider_status_reads_existing_provider_controls_not_new_secrets():
    source = _provider_visibility_source()

    for token in ["ocr_enabled", "mistral_enabled", "ocr_status", "mistral_status"]:
        assert token in source
    assert "save_value(" not in source
    assert "load_value(" not in source


def test_packaged_shell_includes_pdf_review_provider_visibility_mixin():
    source = Path("src/product_intelligence/final_live_ui_desktop.py").read_text(encoding="utf-8")
    assert "PdfReviewProviderVisibilityMixin" in source
    assert "class App(MercadoLibreDesktopMixin, PdfReviewProviderVisibilityMixin" in source
