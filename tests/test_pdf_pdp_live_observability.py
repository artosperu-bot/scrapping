from __future__ import annotations

from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_pipeline import ResolvedPdfIdentity


def test_live_review_surfaces_pdp_search_validation_and_document_events(monkeypatch, tmp_path):
    from product_intelligence import live_pdf_discovery as live

    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    resolved = ResolvedPdfIdentity(
        raw=identity,
        identity=identity,
        official_domain="jbl.com",
        status="RESOLVED",
        confidence=0.99,
        diagnostics={},
    )
    monkeypatch.setattr(live, "resolve_pdf_identity", lambda *_args, **_kwargs: resolved)

    def discover(_identity, **kwargs):
        trace = kwargs.get("trace")
        assert trace is not None
        trace.emit("PDF_PDP_SEARCH", query='site:jbl.com "JBLQ350WLBLKAM"', identifier="JBLQ350WLBLKAM", domain="jbl.com")
        trace.emit("PDF_PDP_VALIDATED", url="https://www.jbl.com/JBLQ350WLBLKAM.html", identity_score=100, authority="MANUFACTURER")
        trace.emit("PDF_LINK_DISCOVERED", url="https://support.jbl.com/Quantum_350_SpecSheet.pdf", landing_url="https://www.jbl.com/JBLQ350WLBLKAM.html", rendered=False)
        return []

    monkeypatch.setattr(live, "discover_review_product_documents", discover)
    events = []

    result = live.discover_validated_review_pdfs_live(identity, tmp_path, on_event=events.append)

    assert result.discovered_count == 0
    assert any(event.get("type") == "pdp" and event.get("stage") == "PDP_SEARCH" for event in events)
    assert any(event.get("type") == "pdp" and event.get("stage") == "PDP_VALIDATED" for event in events)
    assert any(event.get("type") == "document" and event.get("stage") == "DOCUMENT_FOUND" for event in events)
