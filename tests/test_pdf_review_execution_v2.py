from __future__ import annotations

from types import SimpleNamespace

from product_intelligence.document_discovery import DocumentProvenance
from product_intelligence.models import Evidence, ProductIdentity


def _identity():
    return ProductIdentity(brand="JBL", model="Tune 530C", mpn="JBLT530CBLKAM")


def _provenance():
    return DocumentProvenance(
        parent_url="https://uy.jbl.com/JBLT530CBLKAM.html",
        parent_identity_status="EXACT",
        parent_identity_confidence=0.99,
        parent_authority="MANUFACTURER",
        anchor_text="Detailed Instructions",
        discovery_method="exact_pdp_link",
    )


def test_process_pdf_document_accepts_missing_internal_id_only_when_exact_parent_provenance(monkeypatch):
    from product_intelligence import document_ingestion

    ev = Evidence(
        attribute="Driver size",
        raw_value="33 mm",
        normalized_value="33 mm",
        source_url="https://example.test/details.pdf",
        source_type="official_pdf",
        page=3,
        selector="method=TEXT",
        match_level="HIGH",
        confidence=0.9,
    )
    monkeypatch.setattr(document_ingestion, "extract_pdf", lambda *a, **k: ("Driver size: 33 mm", [ev]))
    monkeypatch.setattr(
        document_ingestion,
        "validate_pdf_identity",
        lambda *a, **k: SimpleNamespace(accepted=False, confidence=0.0, reason="strong_identifier_missing"),
    )

    rec = document_ingestion.process_pdf_document(
        _identity(),
        "https://example.test/details.pdf",
        provenance=_provenance(),
    )

    assert rec.fetch["source_decision"]["identity"] == "EXACT"
    assert rec.fetch["identity_reason"] == "identity_bound_by_provenance"
    assert rec.fetch["document_provenance"]["parent_url"].endswith("JBLT530CBLKAM.html")
    assert rec.evidence[0].parent_source_url.endswith("JBLT530CBLKAM.html")
    assert rec.evidence[0].extraction_method == "TEXT"


def test_process_pdf_document_never_uses_provenance_to_override_conflict(monkeypatch):
    import pytest
    from product_intelligence import document_ingestion

    monkeypatch.setattr(document_ingestion, "extract_pdf", lambda *a, **k: ("Other model", []))
    monkeypatch.setattr(
        document_ingestion,
        "validate_pdf_identity",
        lambda *a, **k: SimpleNamespace(accepted=False, confidence=0.0, reason="strong_identifier_conflict"),
    )

    with pytest.raises(ValueError, match="strong_identifier_conflict"):
        document_ingestion.process_pdf_document(
            _identity(),
            "https://example.test/wrong.pdf",
            provenance=_provenance(),
        )


def test_page_quality_uses_more_than_character_count():
    from product_intelligence.pdf_extract import assess_pdf_page_text_quality

    good = assess_pdf_page_text_quality("Technical specifications\nBattery life: 22 hours\nDriver: 40 mm\nFrequency: 20 Hz - 20 kHz")
    garbage = assess_pdf_page_text_quality("@@@ ### ??? !!! " * 20)
    sparse = assess_pdf_page_text_quality("spec")

    assert good.native_ok is True
    assert good.ocr_required is False
    assert garbage.ocr_required is True
    assert sparse.ocr_required is True


def test_pdf_evidence_model_can_trace_parent_and_extraction_method():
    ev = Evidence(
        attribute="Battery",
        raw_value="22 h",
        normalized_value="22 h",
        source_url="https://example.test/manual.pdf",
        source_type="technical_pdf",
        parent_source_url="https://example.test/product",
        page=18,
        extraction_method="OCR",
        raw_snippet="Battery: 22 h",
    )
    assert ev.parent_source_url.endswith("/product")
    assert ev.extraction_method == "OCR"
    assert ev.raw_snippet == "Battery: 22 h"
