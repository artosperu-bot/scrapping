from __future__ import annotations

from product_intelligence.discovery import SearchCandidate
from product_intelligence.models import ProductIdentity


def _identity() -> ProductIdentity:
    return ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")


def test_review_discovery_inspects_exact_official_pdp_before_filetype_pdf_queries(monkeypatch):
    from product_intelligence import pdf_review_search_strategy as strategy

    identity = _identity()
    pdp = SearchCandidate(
        "https://www.jbl.com/JBLQ350WLBLKAM.html",
        "JBL Quantum 350 Wireless",
        "Official product page",
        0.99,
        True,
    )
    linked_pdf = SearchCandidate(
        "https://support.jbl.com/Quantum_350_Wireless_SpecSheet_Spanish.pdf",
        "Spec Sheet Español",
        "document link from exact PDP",
        0.99,
        True,
    )
    queries: list[str] = []

    def search(_identity, query, **_kwargs):
        queries.append(query)
        if query == 'site:jbl.com "JBLQ350WLBLKAM"':
            return [pdp]
        return []

    def resolve(_identity, candidates, **_kwargs):
        assert [row.url for row in candidates] == [pdp.url]
        return [linked_pdf]

    monkeypatch.setattr(strategy.core, "search_web_query_candidates", search)
    monkeypatch.setattr(strategy.core, "_resolve_valid_candidates", resolve)

    rows = strategy.discover_review_product_documents(
        identity,
        official_domain="jbl.com",
        limit=6,
        timeout=1,
    )

    assert [row.url for row in rows] == [linked_pdf.url]
    assert queries[0] == 'site:jbl.com "JBLQ350WLBLKAM"'
    assert not any("filetype:pdf" in query for query in queries)


def test_exact_manufacturer_pdp_can_bind_linked_spec_without_identifier_in_pdf_filename(monkeypatch):
    from product_intelligence import document_discovery as core

    identity = _identity()
    pdp = SearchCandidate(
        "https://www.jbl.com/JBLQ350WLBLKAM.html",
        "JBL Quantum 350 Wireless",
        "Official product page",
        0.99,
        True,
    )

    class Response:
        text = '<html><a href="/docs/Quantum_350_Wireless_SpecSheet_Spanish.pdf">Spec Sheet Español</a></html>'
        def raise_for_status(self):
            return None

    monkeypatch.setattr(core.requests, "get", lambda *_args, **_kwargs: Response())

    rows = core.resolve_document_candidate_urls(identity, pdp, timeout=1)

    assert len(rows) == 1
    assert rows[0].url.endswith("Quantum_350_Wireless_SpecSheet_Spanish.pdf")
    assert "JBLQ350WLBLKAM" not in rows[0].url
    assert rows[0].provenance is not None
    assert rows[0].provenance.parent_url == pdp.url
    assert rows[0].provenance.parent_authority == "MANUFACTURER"
    assert rows[0].provenance.parent_identity_status == "EXACT"
