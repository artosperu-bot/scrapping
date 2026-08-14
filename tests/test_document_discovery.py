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
