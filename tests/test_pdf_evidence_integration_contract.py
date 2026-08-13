from pathlib import Path

def test_batch_pdf_option_defaults_true():
    text=Path('src/product_intelligence/batch.py').read_text(encoding='utf-8')
    assert 'use_pdf_evidence: bool = True' in text

def test_desktop_shows_pdf_option():
    text=Path('src/product_intelligence/desktop.py').read_text(encoding='utf-8')
    assert 'Usar PDFs como evidencia' in text
    assert 'BooleanVar(value=True)' in text
