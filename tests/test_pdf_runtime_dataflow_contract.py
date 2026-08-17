from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_evidence import discover_pdf_candidates
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


def test_social_tracking_pdf_endpoint_is_rejected_before_candidate_extraction():
    html = '''
    <a href="https://connect.facebook.net/en_US/.pdf">Acme Tune 530C manual</a>
    <a href="/docs/acme-tune-530c-manual.pdf">Download manual</a>
    '''
    urls = [row.url for row in discover_pdf_candidates(html, "https://retailer.example/product/abc123")]
    assert "https://connect.facebook.net/en_US/.pdf" not in urls
    assert "https://retailer.example/docs/acme-tune-530c-manual.pdf" in urls


def test_malformed_backslash_pdf_endpoint_is_rejected_before_candidate_extraction():
    html = '''
    <a href="/%5C.pdf">Acme Endurance Run 3 manual</a>
    <a href="/docs/endurance-run-3-manual.pdf">Download manual</a>
    '''
    urls = [row.url for row in discover_pdf_candidates(html, "https://retailer.example/product/abc123")]
    assert "https://retailer.example/%5C.pdf" not in urls
    assert "https://retailer.example/docs/endurance-run-3-manual.pdf" in urls
