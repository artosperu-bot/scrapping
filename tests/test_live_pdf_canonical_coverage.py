from pathlib import Path
from types import SimpleNamespace

from product_intelligence import live_pdf_discovery
from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_review import PdfReviewCandidate


def test_live_discovery_reports_four_language_variants_as_one_unique_document(tmp_path, monkeypatch):
    identity = ProductIdentity(
        brand="JBL",
        model="Quantum 350 Wireless",
        mpn="JBLQ350WLBLKAM",
        match_level="EXACT",
        confidence=.99,
    )
    resolution = SimpleNamespace(
        identity=identity,
        status="RESOLVED",
        source="fixture",
        official_domain="jbl.com",
        trace=[],
    )
    candidates = [
        PdfReviewCandidate(
            url=f"https://support.example/JBL_Quantum_350_Wireless_Specsheet_{language}.pdf",
            title=f"JBL Quantum 350 Wireless Specsheet {language}",
            document_type="datasheet",
            likely_official=True,
            review_score=90,
        )
        for language in ("EN", "DE", "NL", "DA")
    ]

    monkeypatch.setattr(live_pdf_discovery, "resolve_pdf_product_identity", lambda *a, **k: resolution)
    monkeypatch.setattr(live_pdf_discovery, "discover_review_candidates", lambda *a, **k: list(candidates))

    def inspect(_identity, url, cache_dir, **kwargs):
        language = Path(url).stem.rsplit("_", 1)[-1]
        local_path = Path(cache_dir) / f"spec_{language}.pdf"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"%PDF-fixture")
        return SimpleNamespace(
            url=url,
            final_url=url,
            local_path=local_path,
            identity_accepted=True,
            identity_pending_ocr=False,
            identity_provenance_bound=False,
            identity_confidence=.99,
            identity_reason="brand_model",
            identity_relationship="EXACT_MODEL",
            document_scope="MODEL",
            hard_conflicts=(),
            page_count=2,
            native_text_chars=1200,
            ocr_recommended=False,
            preview_png=b"",
            review_score=95,
            selection_allowed=True,
            provenance=None,
        )

    monkeypatch.setattr(live_pdf_discovery, "inspect_pdf_candidate", inspect)

    result = live_pdf_discovery.search_product_pdfs_by_part_number(
        "JBLQ350WLBLKAM",
        output_dir=tmp_path,
        limit=8,
    )

    assert result.validated_count == 4
    assert result.unique_document_count == 1
    assert result.language_variant_count == 4
    assert len(result.canonical_documents) == 1
    assert result.canonical_documents[0]["preferred_language"] == "EN"
    assert result.canonical_documents[0]["variant_count"] == 4
