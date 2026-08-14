from product_intelligence.models import Evidence, ProductIdentity
from product_intelligence.pipeline import ProductPipeline


def test_process_pdf_url_reuses_existing_pdf_evidence_path(monkeypatch):
    identity = ProductIdentity(brand="JBL", model="Quantum 350", mpn="JBLQ350WLBLKAM")
    text = "JBL Quantum 350 JBLQ350WLBLKAM\nDriver size: 40 mm\nWeight: 252 g"
    extracted = [
        Evidence(
            attribute="Driver size",
            raw_value="40 mm",
            normalized_value="40 mm",
            source_url="https://support.jbl.com/q350-manual.pdf",
            source_type="official_pdf",
            match_level="EXACT",
            confidence=.94,
        )
    ]
    monkeypatch.setattr("product_intelligence.pipeline.extract_pdf", lambda url, match_level, confidence: (text, extracted))

    rec = ProductPipeline().process_pdf_url(
        identity,
        "https://support.jbl.com/q350-manual.pdf",
        target_semantics=["Driver size", "Weight"],
    )

    assert rec.identity.mpn == "JBLQ350WLBLKAM"
    assert rec.fetch["source_class"] == "official_pdf"
    assert rec.fetch["direct_document"] is True
    assert "https://support.jbl.com/q350-manual.pdf" in rec.sources
    assert any(ev.attribute == "Driver size" and ev.source_type == "official_pdf" for ev in rec.evidence)


def test_process_pdf_url_rejects_wrong_model(monkeypatch):
    identity = ProductIdentity(brand="JBL", model="Quantum 350", mpn="JBLQ350WLBLKAM")
    monkeypatch.setattr(
        "product_intelligence.pipeline.extract_pdf",
        lambda url, match_level, confidence: ("JBL Quantum 400 user manual", []),
    )
    try:
        ProductPipeline().process_pdf_url(identity, "https://support.jbl.com/quantum400.pdf")
    except ValueError as exc:
        assert "identidad" in str(exc).lower()
    else:
        raise AssertionError("wrong-model PDF must be rejected")
