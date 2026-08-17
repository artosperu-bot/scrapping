from product_intelligence.discovery import SearchCandidate
from product_intelligence.document_discovery import resolve_document_candidate_urls
from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_review_search_strategy import build_review_query_tiers


def _flatten(tiers):
    return [query for tier in tiers for query in tier]


def test_resolved_identity_prioritizes_canonical_document_queries_before_identifier_expansion():
    identity = ProductIdentity(
        brand="Acme",
        manufacturer="Acme Corporation",
        model="Endurance Run 3 Wireless",
        mpn="ABC123XYZ",
    )
    queries = _flatten(build_review_query_tiers(identity, official_domain="acme.com"))
    canonical_positions = [i for i, q in enumerate(queries) if "endurance run 3 wireless" in q.lower()]
    identifier_expansion_positions = [
        i for i, q in enumerate(queries)
        if "abc123xyz" in q.lower()
        and any(term in q.lower() for term in ("manual", "datasheet", "specifications", "support"))
    ]
    assert canonical_positions, queries
    assert identifier_expansion_positions, queries
    assert min(canonical_positions) < min(identifier_expansion_positions), queries
    assert min(canonical_positions) < 4, queries


def test_social_tracking_pdf_endpoint_is_rejected_before_candidate_resolution():
    identity = ProductIdentity(brand="Acme", model="Tune 530C", mpn="ABC123")
    candidate = SearchCandidate(
        url="https://connect.facebook.net/en_US/.pdf",
        title="Acme Tune 530C manual",
        snippet="ABC123 product documentation",
        score=1.0,
    )
    assert resolve_document_candidate_urls(identity, candidate, timeout=1) == []


def test_malformed_backslash_pdf_endpoint_is_rejected_before_candidate_resolution():
    identity = ProductIdentity(brand="Acme", model="Endurance Run 3", mpn="ABC123")
    candidate = SearchCandidate(
        url="https://retailer.example/%5C.pdf",
        title="Acme Endurance Run 3 manual ABC123",
        snippet="Product documentation",
        score=1.0,
    )
    assert resolve_document_candidate_urls(identity, candidate, timeout=1) == []
