from product_intelligence.discovery import SearchCandidate
from product_intelligence.models import ProductIdentity
from product_intelligence import pdf_review


def _identity():
    return ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")


def test_review_hides_generic_third_party_pdf_that_only_inherits_parent_identity(monkeypatch):
    row = pdf_review.SimpleNamespace if False else None
    from product_intelligence.document_discovery import DocumentSearchCandidate

    generic = DocumentSearchCandidate(
        url="https://retailer.example/files/Specification_Sheet.pdf",
        title="Specification Sheet",
        snippet="document link from https://retailer.example/product/JBLQ350WLBLKAM",
        score=0.9,
        likely_official=False,
        provenance=None,
        identity_status="EXACT",
        identity_reason="exact_strong_identifier",
        identity_score=100,
    )
    monkeypatch.setattr(pdf_review, "discover_product_documents", lambda *_a, **_k: [generic])

    rows = pdf_review.discover_review_candidates(_identity(), limit=8)

    assert rows == []


def test_review_keeps_third_party_pdf_when_child_itself_proves_exact_identity(monkeypatch):
    from product_intelligence.document_discovery import DocumentSearchCandidate

    exact = DocumentSearchCandidate(
        url="https://retailer.example/files/JBLQ350WLBLKAM_Specification_Sheet.pdf",
        title="JBLQ350WLBLKAM Specification Sheet",
        snippet="document link from https://retailer.example/product/JBLQ350WLBLKAM",
        score=0.9,
        likely_official=False,
        provenance=None,
        identity_status="EXACT",
        identity_reason="exact_strong_identifier",
        identity_score=100,
    )
    monkeypatch.setattr(pdf_review, "discover_product_documents", lambda *_a, **_k: [exact])

    rows = pdf_review.discover_review_candidates(_identity(), limit=8)

    assert len(rows) == 1
    assert rows[0].url == exact.url
    assert rows[0].identity_status == "EXACT"
    assert rows[0].identity_score == 100
