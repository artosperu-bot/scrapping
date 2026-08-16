from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import fitz

from product_intelligence.models import ProductIdentity


def _identity() -> ProductIdentity:
    return ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")


def _pdf(path: Path, pages: int = 3) -> Path:
    doc = fitz.open()
    for idx in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"JBL Quantum 350 Wireless JBLQ350WLBLKAM page {idx + 1}")
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


def test_search_snippet_echo_of_mpn_does_not_prove_exact_identity():
    from product_intelligence.document_discovery import assess_document_candidate

    result = assess_document_candidate(
        _identity(),
        "https://manuals.plus/asin/B098R6CLQ6.pdf",
        "Wireless Headphones User Manual",
        "Search result for JBLQ350WLBLKAM manual and related products",
    )

    assert result.accepted is False
    assert result.exact_strong_id is False
    assert result.reason == "snippet_only_strong_identifier"


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


def test_third_party_provenance_cannot_promote_missing_identity():
    from product_intelligence.document_discovery import DocumentProvenance, can_bind_document_by_provenance

    provenance = DocumentProvenance(
        parent_url="https://www.loyaltysource.com/product/JBLT530CBLKAM",
        parent_identity_status="EXACT",
        parent_identity_confidence=0.99,
        parent_authority="VALIDATED_SOURCE",
        anchor_text="Detailed Instructions",
        discovery_method="exact_pdp_link",
    )

    assert can_bind_document_by_provenance(provenance, internal_identity_reason="strong_identifier_missing") is False


def test_mpn_used_as_model_does_not_generate_self_join_query():
    from product_intelligence.document_discovery import build_document_queries

    identity = ProductIdentity(brand="JBL", model="JBLENDURRUN3BTBAM", mpn="JBLENDURRUN3BTBAM")
    queries = build_document_queries(identity)

    assert '"JBLENDURRUN3BTBAM" "JBLENDURRUN3BTBAM" filetype:pdf' not in queries
    assert len(queries) == len(set(queries))


def test_discovery_has_global_landing_inspection_budget(monkeypatch):
    from product_intelligence.discovery import SearchCandidate
    from product_intelligence import document_discovery as discovery

    identity = _identity()
    rows = [
        SearchCandidate(
            f"https://support.example/JBLQ350WLBLKAM/page-{idx}.html",
            f"JBLQ350WLBLKAM support page {idx}",
            "JBL Quantum 350 Wireless support",
            0.9,
            True,
        )
        for idx in range(20)
    ]
    monkeypatch.setattr(discovery, "search_web_query_candidates", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(discovery, "search_web", lambda *_args, **_kwargs: [])
    inspected: list[str] = []

    def no_pdf(_identity, candidate, **_kwargs):
        inspected.append(candidate.url)
        return []

    monkeypatch.setattr(discovery, "resolve_document_candidate_urls", no_pdf)

    assert discovery.discover_product_documents(identity, limit=6, timeout=1) == []
    assert len(inspected) <= discovery.MAX_LANDING_INSPECTIONS


def test_discovery_has_global_query_budget(monkeypatch):
    from product_intelligence import document_discovery as discovery

    queries: list[str] = []

    def no_results(_identity, query, **_kwargs):
        queries.append(query)
        return []

    monkeypatch.setattr(discovery, "search_web_query_candidates", no_results)
    monkeypatch.setattr(discovery, "browser_search", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(discovery, "search_web", lambda *_args, **_kwargs: [])

    assert discovery.discover_product_documents(_identity(), limit=6, timeout=1) == []
    assert len(queries) <= discovery.MAX_QUERY_ATTEMPTS


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


def test_pdf_over_ten_pages_is_rejected_from_manual_selection(monkeypatch, tmp_path):
    from product_intelligence import pdf_review

    source = _pdf(tmp_path / "too-long.pdf", pages=11)
    monkeypatch.setattr(
        pdf_review,
        "download_pdf",
        lambda url, *_args, **_kwargs: SimpleNamespace(path=source, final_url=url),
    )

    inspection = pdf_review.inspect_pdf_candidate(
        _identity(),
        "https://www.jbl.com/JBLQ350WLBLKAM-too-long.pdf",
        tmp_path / "cache",
        likely_official=True,
        identity_score=100,
    )

    assert inspection.page_count == 11
    assert inspection.selection_allowed is False
    assert inspection.identity_accepted is False
    assert inspection.identity_pending_ocr is False
    assert inspection.identity_reason == "page_limit_exceeded"


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
