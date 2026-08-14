from product_intelligence.discovery import SearchCandidate
from product_intelligence.document_discovery import (
    build_document_queries,
    classify_document_candidate,
    discover_product_documents,
    identity_matches_document,
)
from product_intelligence.models import ProductIdentity


def _identity():
    return ProductIdentity(brand="JBL", model="Quantum 350", mpn="JBLQ350WLBLKAM")


def test_build_document_queries_cover_manual_datasheet_and_mpn():
    queries = build_document_queries(_identity())
    joined = "\n".join(queries).lower()
    assert '"jbl quantum 350" manual pdf' in joined
    assert '"jbl quantum 350" datasheet pdf' in joined
    assert '"jblq350wlblkam" manual pdf' in joined
    assert '"jblq350wlblkam"' in [q.lower() for q in queries]
    assert '"jblq350wlblkam" support downloads' in joined
    assert len(queries) == len(set(queries))


def test_classification_requires_document_semantics_not_pdf_extension_alone():
    assert classify_document_candidate(
        "https://support.jbl.com/quantum350-user-manual.pdf",
        "JBL Quantum 350 User Manual",
        "Official user guide",
    ) == "manual"
    assert classify_document_candidate(
        "https://cdn.example.com/random.pdf",
        "JBL Quantum 350 promotional brochure",
        "Buy now",
    ) is None


def test_identity_match_accepts_strong_identifier_or_brand_model():
    identity = _identity()
    assert identity_matches_document(
        identity,
        "https://support.jbl.com/JBLQ350WLBLKAM/manual.pdf",
        "Quantum 350 manual",
        "",
    )
    assert identity_matches_document(
        identity,
        "https://support.jbl.com/manual.pdf",
        "JBL Quantum 350 User Manual",
        "Official documentation",
    )
    assert not identity_matches_document(
        identity,
        "https://support.jbl.com/manual.pdf",
        "JBL Quantum 400 User Manual",
        "Quantum 400",
    )


def test_discover_product_documents_filters_dedupes_and_keeps_metadata(monkeypatch):
    rows = [
        SearchCandidate("https://support.jbl.com/q350-manual.pdf", "JBL Quantum 350 User Manual", "JBLQ350WLBLKAM", .9, True),
        SearchCandidate("https://support.jbl.com/q350-manual.pdf", "duplicate", "JBLQ350WLBLKAM", .8, True),
        SearchCandidate("https://cdn.example.com/random.pdf", "JBL Quantum 350 brochure", "sale", .7, False),
        SearchCandidate("https://support.jbl.com/q400-manual.pdf", "JBL Quantum 400 User Manual", "Quantum 400", .95, True),
        SearchCandidate("https://support.jbl.com/q350-datasheet.pdf", "JBL Quantum 350 Datasheet", "JBLQ350WLBLKAM specs", .88, True),
    ]

    monkeypatch.setattr(
        "product_intelligence.document_discovery.search_web_query_candidates",
        lambda identity, query, limit=8, timeout=15: rows,
    )
    found = discover_product_documents(_identity(), limit=8, timeout=1)
    assert [row.url for row in found] == [
        "https://support.jbl.com/q350-manual.pdf",
        "https://support.jbl.com/q350-datasheet.pdf",
    ]
    assert found[0].likely_official is True


def _patch_landing_html(monkeypatch):
    class Response:
        text = """
        <html><body>
          <a href="/downloads/JBL_Quantum350_SpecSheet.pdf">Spec Sheet</a>
          <a href="/downloads/JBL_Quantum350_OwnersManual.pdf">Owners Manual</a>
          <a href="/privacy.pdf">Privacy policy</a>
        </body></html>
        """

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "product_intelligence.document_discovery.requests.get",
        lambda *args, **kwargs: Response(),
    )


def test_pdf_only_discovery_opens_identity_matched_product_page_to_find_real_pdfs(monkeypatch):
    landing = SearchCandidate(
        "https://global.jbl.com/gaming-headsets/JBLQ350WLBLKAM.html",
        "JBL Quantum 350 Wireless",
        "JBLQ350WLBLKAM",
        .95,
        True,
    )

    monkeypatch.setattr(
        "product_intelligence.document_discovery.search_web_query_candidates",
        lambda identity, query, limit=8, timeout=15: [landing],
    )
    _patch_landing_html(monkeypatch)

    found = discover_product_documents(_identity(), limit=8, timeout=1)
    assert [row.url for row in found] == [
        "https://global.jbl.com/downloads/JBL_Quantum350_SpecSheet.pdf",
        "https://global.jbl.com/downloads/JBL_Quantum350_OwnersManual.pdf",
    ]


def test_pdf_only_falls_back_to_real_product_search_when_document_queries_return_zero(monkeypatch):
    landing = SearchCandidate(
        "https://www.jbl.com.pe/JBLQ350WLBLKAM.html",
        "JBL Quantum 350 Wireless",
        "JBLQ350WLBLKAM",
        .99,
        True,
    )
    monkeypatch.setattr(
        "product_intelligence.document_discovery.search_web_query_candidates",
        lambda identity, query, limit=8, timeout=15: [],
    )
    monkeypatch.setattr(
        "product_intelligence.document_discovery.search_web",
        lambda identity, limit=12, timeout=20: [landing],
    )
    _patch_landing_html(monkeypatch)

    found = discover_product_documents(_identity(), limit=8, timeout=1)
    assert [row.url for row in found] == [
        "https://www.jbl.com.pe/downloads/JBL_Quantum350_SpecSheet.pdf",
        "https://www.jbl.com.pe/downloads/JBL_Quantum350_OwnersManual.pdf",
    ]
