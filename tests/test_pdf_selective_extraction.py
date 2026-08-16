from __future__ import annotations

import product_intelligence.pdf_extract as pdf_extract


def _selector():
    selector = getattr(pdf_extract, "select_pdf_page_indexes", None)
    assert selector is not None, "select_pdf_page_indexes must exist"
    return selector


def test_short_pdf_selects_every_page():
    page_texts = [f"Page {index} content" for index in range(10)]

    selected = _selector()(page_texts, focus_terms=["MODEL-X"])

    assert selected == list(range(10))


def test_long_pdf_is_bounded_but_keeps_late_exact_model_page():
    page_texts = [f"General manual page {index}" for index in range(40)]
    page_texts[27] = "MODEL-X technical specifications battery capacity dimensions"

    selected = _selector()(page_texts, focus_terms=["MODEL-X"])

    assert len(selected) <= 15
    assert list(range(8)) == selected[:8]
    assert 27 in selected


def test_long_pdf_prioritizes_technical_pages_after_head_pages():
    page_texts = [f"General instructions page {index}" for index in range(30)]
    page_texts[18] = "Technical specifications: display processor memory battery dimensions"
    page_texts[24] = "Warranty and legal notices"

    selected = _selector()(page_texts)

    assert len(selected) <= 15
    assert 18 in selected
    assert 24 not in selected
