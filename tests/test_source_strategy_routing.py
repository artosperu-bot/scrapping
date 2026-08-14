from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "product_intelligence"


def test_source_strategy_defaults_and_dependencies():
    from product_intelligence.source_strategy import SourceStrategy

    default = SourceStrategy().normalized()
    assert default.web is True
    assert default.pdf is True
    assert default.ocr is True
    assert default.mistral is True

    no_pdf = SourceStrategy(web=True, pdf=False, ocr=True, mistral=True).normalized()
    assert no_pdf.pdf is False
    assert no_pdf.ocr is False
    assert no_pdf.mistral is True

    with pytest.raises(ValueError, match="SOURCE_STRATEGY_REQUIRES_WEB_OR_PDF"):
        SourceStrategy(web=False, pdf=False).normalized()


def test_batch_accepts_source_strategy_and_has_route_guards():
    source = (SRC / "batch.py").read_text(encoding="utf-8")
    assert "from .source_strategy import SourceStrategy" in source
    assert "source_strategy: SourceStrategy | None = None" in source
    assert "strategy = (source_strategy or SourceStrategy()).normalized()" in source
    assert "if strategy.web" in source
    assert "if strategy.pdf" in source
    assert "if strategy.web and gap_terms" in source


def test_solo_pdf_has_direct_document_bootstrap_before_no_source_failure():
    source = (SRC / "batch.py").read_text(encoding="utf-8")
    bootstrap = source.index("if not accepted and strategy.pdf:")
    no_source = source.index("if not accepted:")
    assert bootstrap < no_source
    assert "_ingest_direct_documents(" in source[bootstrap:no_source]

    helper = source.split("def _ingest_direct_documents", 1)[1].split("\n\ndef ", 1)[0]
    assert "document_candidates = discover_product_documents(identity" in helper
    assert "process_pdf_document(" in helper


def test_web_off_skips_non_pdf_manual_urls():
    source = (SRC / "batch.py").read_text(encoding="utf-8")
    assert "_looks_like_pdf_url" in source
    assert "if strategy.web or (strategy.pdf and _looks_like_pdf_url(u))" in source
