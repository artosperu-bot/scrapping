from product_intelligence.models import ProductIdentity
from product_intelligence.price_peru_coverage import _general_retail_queries


def test_verified_brand_and_mpn_add_two_country_scope_queries_only():
    queries = _general_retail_queries(ProductIdentity(brand="ExampleBrand", mpn="ABC/123"))
    assert '"ExampleBrand" "ABC/123" site:.pe' in queries
    assert '"ExampleBrand" "ABC/123" site:.com.pe' in queries
    brand_mpn_scope = [q for q in queries if q.startswith('"ExampleBrand" "ABC/123" site:')]
    assert brand_mpn_scope == [
        '"ExampleBrand" "ABC/123" site:.pe',
        '"ExampleBrand" "ABC/123" site:.com.pe',
    ]


def test_mpn_only_without_resolved_brand_does_not_invent_brand_scope():
    queries = _general_retail_queries(ProductIdentity(mpn="ABC/123"))
    assert not any(q.startswith('"ExampleBrand"') for q in queries)
