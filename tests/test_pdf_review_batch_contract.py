from pathlib import Path

from product_intelligence.batch import BatchItem, scrape_item
from product_intelligence.models import ProductIdentity, ProductRecord
from product_intelligence.source_strategy import SourceStrategy


def _record(identity, url):
    rec = ProductRecord(identity=identity.model_copy(deep=True), sources=[url])
    rec.identity.match_level = "EXACT"
    rec.fetch = {
        "source_class": "manufacturer",
        "source_decision": {
            "page_type": "PRODUCT",
            "material_allowed": True,
            "identity": "EXACT",
            "identity_confidence": 0.99,
            "authority": "manufacturer",
            "authority_confidence": 0.99,
        },
    }
    return rec


def test_reviewed_pdf_selection_disables_automatic_pdf_discovery_but_keeps_web(tmp_path, monkeypatch):
    import product_intelligence.batch as batch

    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    html_url = "https://www.jbl.test/quantum-350"
    approved_pdf = "https://www.jbl.test/manual-q350.pdf"
    calls = {"html_include_pdfs": [], "direct_discovery": 0, "approved_pdf": 0}

    candidate = type(
        "Candidate",
        (),
        {"url": html_url, "likely_official": True, "score": 1.0, "manual_source": False},
    )()
    monkeypatch.setattr(batch, "search_web", lambda *args, **kwargs: [candidate])
    monkeypatch.setattr(batch, "search_web_for_fields", lambda *args, **kwargs: [])
    monkeypatch.setattr(batch, "analyze_resolution", lambda *args, **kwargs: {"blocked": False, "research_terms": [], "fields": [], "cross_field_issues": []})
    monkeypatch.setattr(batch, "_merge_valid_records", lambda records: records[0])

    def process_url(_self, _expected, url, **kwargs):
        calls["html_include_pdfs"].append(kwargs["include_pdfs"])
        return _record(identity, url)

    monkeypatch.setattr(batch.ProductPipeline, "process_url", process_url)

    def process_pdf(_identity, url, **kwargs):
        assert url == approved_pdf
        calls["approved_pdf"] += 1
        return _record(identity, url)

    monkeypatch.setattr(batch, "process_pdf_document", process_pdf)

    def forbidden_direct(*args, **kwargs):
        calls["direct_discovery"] += 1
        raise AssertionError("automatic direct PDF discovery must not run for confirmed review")

    monkeypatch.setattr(batch, "_ingest_direct_documents", forbidden_direct)

    item = BatchItem(
        row=2,
        sheet="Sheet1",
        identity=identity,
        reviewed_pdf_urls=[approved_pdf],
        pdf_review_enforced=True,
    )
    result = scrape_item(
        item,
        str(tmp_path),
        template_plan={"media_slots": 0, "scrape_semantics": [], "summary": {"scrape_targets": 1}},
        source_strategy=SourceStrategy(web=True, pdf=True, ocr=False, mistral=False),
    )

    assert result is not None
    assert calls["approved_pdf"] == 1
    assert calls["html_include_pdfs"] and all(value is False for value in calls["html_include_pdfs"])
    assert calls["direct_discovery"] == 0


def test_unreviewed_product_preserves_automatic_pdf_behavior():
    item = BatchItem(
        row=2,
        sheet="Sheet1",
        identity=ProductIdentity(model="Example"),
    )
    assert item.pdf_review_enforced is False
    assert item.reviewed_pdf_urls in (None, [])
