from types import SimpleNamespace

import fitz

from product_intelligence.models import ProductIdentity, ProductRecord
from product_intelligence.pipeline import ProductPipeline


def _pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_pipeline_rejects_sibling_pdf_before_full_extraction(monkeypatch):
    from product_intelligence import media_discovery, pipeline

    expected = ProductIdentity(
        brand="JBL",
        manufacturer="JBL",
        product_name="JBL Endurance Run 3 Wireless",
        model="Endurance Run 3 Wireless",
        variant="Wireless",
        match_level="EXACT",
        confidence=.99,
    )
    product_url = "https://www.jbl.example/endurance-run-3-wireless"
    sibling_url = "https://www.jbl.example/JBL_Endurance_Run_3_Specsheet_EN.pdf"
    sibling_bytes = _pdf_bytes(
        "JBL Endurance Run 3 Wired Sport Headphones. 3.5 mm audio cable."
    )

    fetch = SimpleNamespace(
        status_code=200,
        html="<html>product</html>",
        final_url=product_url,
        method="requests",
        json_responses=[],
        network_resources=[],
        warnings=[],
    )
    page = {
        "text": "JBL Endurance Run 3 Wireless Bluetooth sport headphones",
        "pdfs": [sibling_url],
        "document_links": [],
    }
    page_assessment = SimpleNamespace(
        material_allowed=True,
        page_type="PRODUCT",
        confidence=.99,
        reasons=(),
    )
    identity_assessment = SimpleNamespace(
        status="EXACT",
        confidence=.99,
        reasons=(),
        matched_identifiers=(),
        conflicting_identifiers=(),
    )
    authority = SimpleNamespace(
        source_class="manufacturer",
        confidence=.99,
        reasons=(),
    )
    browser = SimpleNamespace(
        needed=False,
        reason="STATIC_SUFFICIENT",
        target_hits=0,
        target_total=0,
    )

    monkeypatch.setattr(pipeline, "fetch_page", lambda *a, **k: fetch)
    monkeypatch.setattr(pipeline, "extract_page", lambda *a, **k: page)
    monkeypatch.setattr(pipeline, "derive_page_signals", lambda *a, **k: object())
    monkeypatch.setattr(pipeline, "classify_page_type", lambda *a, **k: page_assessment)
    monkeypatch.setattr(pipeline, "derive_observed_identity", lambda *a, **k: expected.model_copy(deep=True))
    monkeypatch.setattr(pipeline, "assess_identity", lambda *a, **k: identity_assessment)
    monkeypatch.setattr(pipeline, "derive_authority_signals", lambda *a, **k: object())
    monkeypatch.setattr(pipeline, "classify_source_authority", lambda *a, **k: authority)
    monkeypatch.setattr(pipeline, "identity_from_page", lambda *a, **k: expected.model_copy(deep=True))
    monkeypatch.setattr(pipeline, "compare_identity", lambda *a, **k: expected.model_copy(deep=True))
    monkeypatch.setattr(pipeline, "browser_decision", lambda *a, **k: browser)
    monkeypatch.setattr(pipeline, "structured_evidence", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "table_evidence", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "extract_target_evidence", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "extract_text_evidence", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "source_evidence", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "extract_technical_notes", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "discover_media", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "build_site_profile", lambda *a, **k: {})
    monkeypatch.setattr(pipeline, "build_evidence_graph", lambda *a, **k: {})
    monkeypatch.setattr(
        pipeline,
        "build_record_strict",
        lambda identity, evidence, sources: ProductRecord(
            identity=identity.model_copy(deep=True), evidence=list(evidence), sources=list(sources)
        ),
    )
    monkeypatch.setattr(
        media_discovery,
        "validate_resource_identity",
        lambda *a, **k: ("EXACT_PRODUCT", .99, (), ()),
    )

    legacy_extract_calls = []
    full_extract_calls = []
    download_calls = []

    def legacy_extract(url, *args, **kwargs):
        legacy_extract_calls.append(url)
        return (
            "JBL Endurance Run 3 Wired Sport Headphones. 3.5 mm audio cable.",
            [],
        )

    def full_extract(data, source_url, **kwargs):
        full_extract_calls.append(source_url)
        return "SHOULD NOT RUN", []

    monkeypatch.setattr(pipeline, "extract_pdf", legacy_extract, raising=False)
    monkeypatch.setattr(
        pipeline,
        "download_bytes",
        lambda url: (download_calls.append(url) or sibling_bytes),
        raising=False,
    )
    monkeypatch.setattr(pipeline, "extract_pdf_bytes", full_extract, raising=False)

    result = ProductPipeline().process_url(
        expected,
        product_url,
        include_pdfs=True,
        include_images=False,
        browser_fallback=False,
    )

    assert download_calls == [sibling_url]
    assert legacy_extract_calls == []
    assert full_extract_calls == []
    assert result.fetch["official_pdfs_followed"] == 0
