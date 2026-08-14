import fitz

from product_intelligence.description_narrator import DescriptionGuard, build_safe_facts
from product_intelligence.pdf_extract import _extract_document
from product_intelligence.provider_runtime import current_settings, emit, provider_run_scope

from test_provider_ocr_mistral_integration import _record


def test_native_pdf_text_does_not_call_ocr():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Native specification text is already available")
    calls = []
    pages = _extract_document(doc, ocr_page=lambda number, image: calls.append(number) or "OCR")
    doc.close()
    assert calls == []
    assert pages[0].method == "TEXT"
    assert "Native specification" in pages[0].text


def test_empty_pdf_page_uses_ocr_seam():
    doc = fitz.open()
    doc.new_page()
    calls = []
    pages = _extract_document(doc, ocr_page=lambda number, image: calls.append(number) or "Scanned: value")
    doc.close()
    assert calls == [1]
    assert pages[0].method == "OCR"
    assert pages[0].text == "Scanned: value"


def test_ocr_exception_does_not_break_pdf_extraction():
    doc = fitz.open()
    doc.new_page()

    def fail(number, image):
        raise RuntimeError("OCR unavailable")

    pages = _extract_document(doc, ocr_page=fail)
    doc.close()
    assert len(pages) == 1
    assert pages[0].text == ""


def test_provider_run_scope_copies_settings_and_restores_context():
    supplied = {
        "ocr_space_enabled": True,
        "mistral_enabled": True,
        "mistral_model": "mistral-small-latest",
        "request_timeout": 31,
    }
    before = current_settings()
    with provider_run_scope(supplied):
        supplied["request_timeout"] = 99
        assert current_settings()["request_timeout"] == 31
        assert current_settings()["mistral_model"] == "mistral-small-latest"
    assert current_settings() == before


def test_provider_audit_filters_secret_fields():
    events = []
    with provider_run_scope({}, lambda event, data: events.append((event, data))):
        emit("SAFE_EVENT", provider="OCR.space", token="hidden", secret="hidden", headers="hidden")
    assert events == [("SAFE_EVENT", {"provider": "OCR.space"})]


def test_guard_rejects_new_material_certification_compatibility_and_mpn():
    rec = _record()
    facts = build_safe_facts(rec)
    guard = DescriptionGuard()
    bad = [
        "JBL Quantum 350 Wireless fabricado en titanio con driver de 40 mm.",
        "JBL Quantum 350 Wireless con certificación MIL-STD y driver de 40 mm.",
        "JBL Quantum 350 Wireless compatible con PlayStation y driver de 40 mm.",
        "JBL Quantum 350 Wireless, MPN OTRO-CODIGO, con driver de 40 mm.",
    ]
    assert all(guard.validate(text, rec, facts).accepted is False for text in bad)
