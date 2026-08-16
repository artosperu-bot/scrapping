from types import SimpleNamespace

from product_intelligence.discovery import SearchCandidate
from product_intelligence.models import ProductIdentity
from product_intelligence import document_discovery as discovery


def _identity():
    return ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")


def test_third_party_landing_does_not_transfer_exact_identity_to_generic_pdf(monkeypatch):
    parent = discovery.DocumentSearchCandidate(
        url="https://retailer.example/product/JBLQ350WLBLKAM",
        title="JBL Quantum 350 Wireless JBLQ350WLBLKAM",
        snippet="",
        score=0.9,
        likely_official=False,
        identity_status="EXACT",
        identity_reason="exact_strong_identifier",
        identity_score=100,
    )
    monkeypatch.setattr(
        discovery.requests,
        "get",
        lambda *_a, **_k: SimpleNamespace(text="<html></html>", raise_for_status=lambda: None),
    )
    monkeypatch.setattr(
        discovery,
        "discover_pdf_candidates",
        lambda *_a, **_k: [SimpleNamespace(url="https://retailer.example/files/Specification_Sheet.pdf", label="Specification Sheet")],
    )
    monkeypatch.setattr(discovery, "browser_pdf_links", lambda *_a, **_k: [])

    rows = discovery.resolve_document_candidate_urls(_identity(), parent, timeout=1)

    assert rows == []


def test_third_party_pdf_with_own_exact_identifier_is_allowed(monkeypatch):
    parent = discovery.DocumentSearchCandidate(
        url="https://retailer.example/product/JBLQ350WLBLKAM",
        title="JBL Quantum 350 Wireless JBLQ350WLBLKAM",
        snippet="",
        score=0.9,
        likely_official=False,
        identity_status="EXACT",
        identity_reason="exact_strong_identifier",
        identity_score=100,
    )
    child = "https://retailer.example/files/JBLQ350WLBLKAM_Specification_Sheet.pdf"
    monkeypatch.setattr(
        discovery.requests,
        "get",
        lambda *_a, **_k: SimpleNamespace(text="<html></html>", raise_for_status=lambda: None),
    )
    monkeypatch.setattr(
        discovery,
        "discover_pdf_candidates",
        lambda *_a, **_k: [SimpleNamespace(url=child, label="JBLQ350WLBLKAM Specification Sheet")],
    )
    monkeypatch.setattr(discovery, "browser_pdf_links", lambda *_a, **_k: [])

    rows = discovery.resolve_document_candidate_urls(_identity(), parent, timeout=1)

    assert len(rows) == 1
    assert rows[0].url == child
    assert rows[0].identity_status == "EXACT"
    assert rows[0].identity_score == 100
