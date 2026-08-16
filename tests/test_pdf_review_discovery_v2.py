from __future__ import annotations

from pathlib import Path

import fitz

from product_intelligence.models import ProductIdentity


def _identity() -> ProductIdentity:
    return ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")


def _pdf(path: Path, pages: int = 3) -> Path:
    doc = fitz.open()
    for idx in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"JBL Quantum 350 Wireless page {idx + 1}")
    doc.save(path)
    doc.close()
    return path


def test_query_tiers_start_with_strong_identifier_and_delay_broad_fallback():
    from product_intelligence.document_discovery import build_document_query_tiers

    tiers = build_document_query_tiers(_identity(), official_domain="jbl.com")

    assert len(tiers) >= 4
    assert any('"JBLQ350WLBLKAM"' in query for query in tiers[0])
    assert any("site:jbl.com" in query for query in tiers[0] + tiers[1])
    broad = " ".join(tiers[-1]).lower()
    assert "quantum 350" in broad


def test_sibling_model_is_rejected_before_fetch():
    from product_intelligence.document_discovery import assess_document_candidate

    result = assess_document_candidate(
        _identity(),
        "https://manuals.example/jbl-pulse-3-manual.pdf",
        "JBL Pulse 3 User Manual",
        "Manual for JBL Pulse 3 portable speaker",
    )

    assert result.accepted is False
    assert result.conflict is True
    assert result.reason in {"sibling_model_conflict", "strong_identifier_conflict"}


def test_brand_only_generic_page_is_not_a_product_candidate():
    from product_intelligence.document_discovery import assess_document_candidate

    result = assess_document_candidate(
        _identity(),
        "https://example.test/jbl/headphones.html",
        "JBL Headphones",
        "Browse all JBL headphones",
    )

    assert result.accepted is False
    assert result.reason == "brand_only_or_generic"


def test_exact_mpn_is_high_confidence_candidate():
    from product_intelligence.document_discovery import assess_document_candidate

    result = assess_document_candidate(
        _identity(),
        "https://www.jbl.com/JBLQ350WLBLKAM.html",
        "JBL Quantum 350 Wireless Gaming Headset",
        "JBLQ350WLBLKAM support and downloads",
    )

    assert result.accepted is True
    assert result.exact_strong_id is True
    assert result.identity_score >= 90


def test_document_provenance_can_bind_missing_internal_identifier_without_overriding_conflict():
    from product_intelligence.document_discovery import DocumentProvenance, can_bind_document_by_provenance

    provenance = DocumentProvenance(
        parent_url="https://www.jbl.com/JBLQ350WLBLKAM.html",
        parent_identity_status="EXACT",
        parent_identity_confidence=0.99,
        parent_authority="MANUFACTURER",
        anchor_text="Detailed Instructions",
        discovery_method="exact_pdp_link",
    )

    assert can_bind_document_by_provenance(provenance, internal_identity_reason="strong_identifier_missing") is True
    assert can_bind_document_by_provenance(provenance, internal_identity_reason="strong_identifier_conflict") is False


def test_review_discovery_does_not_download_pdf(monkeypatch):
    from product_intelligence import pdf_review
    from product_intelligence.discovery import SearchCandidate

    monkeypatch.setattr(
        pdf_review,
        "discover_product_documents",
        lambda *_args, **_kwargs: [SearchCandidate("https://example.test/manual.pdf", "Quantum 350 Manual", "JBLQ350WLBLKAM", 0.9, True)],
    )
    monkeypatch.setattr(pdf_review, "download_pdf", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("download not allowed during discovery")))

    rows = pdf_review.discover_review_candidates(_identity(), limit=5)

    assert len(rows) == 1
    assert rows[0].url.endswith("manual.pdf")


def test_render_pdf_page_supports_arbitrary_page_and_zoom(tmp_path):
    from product_intelligence.pdf_review import render_pdf_page

    source = _pdf(tmp_path / "multi.pdf", pages=3)
    first = render_pdf_page(source, 0, 1.0)
    third = render_pdf_page(source, 2, 1.5)

    assert first.startswith(b"\x89PNG")
    assert third.startswith(b"\x89PNG")
    assert first != third


def test_review_shell_exposes_full_reader_controls():
    source = Path("src/product_intelligence/pdf_review_shell.py").read_text(encoding="utf-8")

    for token in [
        "Primera",
        "Anterior",
        "Siguiente",
        "Última",
        "Página",
        "Ajustar ancho",
        "Ajustar página",
        "<Control-MouseWheel>",
        "Canvas",
    ]:
        assert token in source


def test_review_shell_exposes_reviewed_and_automatic_modes():
    source = Path("src/product_intelligence/pdf_review_shell.py").read_text(encoding="utf-8")
    assert "Revisar antes de usar" in source
    assert "Automático" in source
    assert "reviewed" in source
    assert "automatic" in source
