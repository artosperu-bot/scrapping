from pathlib import Path


def test_pdf_option_defaults_true():
    text=Path('src/product_intelligence/pdf_desktop.py').read_text(encoding='utf-8')
    assert 'Usar PDFs como evidencia' in text
    assert 'BooleanVar(value=True)' in text
    assert 'use_pdf_evidence' in text


def test_entrypoint_uses_pdf_desktop_and_keeps_modern_contract():
    text=Path('run_desktop.py').read_text(encoding='utf-8')
    assert 'product_intelligence.modern_desktop import main' in text
    assert 'product_intelligence.pdf_desktop' in text


def test_pyinstaller_includes_dynamic_pdf_desktop_module():
    text=Path('ProductIntelligence.spec').read_text(encoding='utf-8')
    assert "'product_intelligence.pdf_desktop'" in text
