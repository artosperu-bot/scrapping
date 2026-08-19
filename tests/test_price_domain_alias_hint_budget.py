from product_intelligence.models import ProductIdentity
from product_intelligence import price_peru_coverage
from product_intelligence.price_peru_coverage import _general_retail_queries


def test_domain_hint_mpn_alias_family_is_bounded_to_three_queries_per_domain():
    identity = ProductIdentity(mpn="ABC/123")
    learned = "learned.example.pe"
    known = price_peru_coverage.PERU_RETAIL_HINT_DOMAINS[0]
    queries = _general_retail_queries(identity, priority_domains=(learned,))

    for domain in (learned, known):
        domain_queries = [query for query in queries if query.endswith(f"site:{domain}")]
        assert len(domain_queries) == 3
        assert f'"ABC/123" site:{domain}' in domain_queries
        assert f'"ABC123" site:{domain}' in domain_queries
        assert f'"ABC-123" site:{domain}' in domain_queries
