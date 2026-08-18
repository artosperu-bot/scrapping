from product_intelligence.models import ProductIdentity
from product_intelligence.price_peru_coverage import _general_retail_queries, _queries
from product_intelligence.price_workflow import _mercadolibre_queries


def test_directed_domain_queries_use_mpn_separator_aliases():
    identity = ProductIdentity(brand="ExampleBrand", model="Model 123", mpn="ABC/123")
    queries = _queries(identity, "shop.example.pe")
    assert any('"ABC/123" site:shop.example.pe' == q for q in queries)
    assert any('"ABC123" site:shop.example.pe' == q for q in queries)
    assert any('"ABC-123" site:shop.example.pe' == q for q in queries)
    assert any('"ABC 123" site:shop.example.pe' == q for q in queries)


def test_open_peru_queries_include_verified_barcode_and_brand_model_without_case_noise():
    identity = ProductIdentity(
        brand="ExampleBrand", model="Model 123", mpn="ABC/123", upc="036000291452"
    )
    queries = _general_retail_queries(identity)
    joined = "\n".join(queries)
    assert '"ABC123" precio Perú' in joined
    assert '"036000291452" precio Perú' in joined
    assert '"Model 123"' in joined
    assert len(queries) == len(set(q.casefold() for q in queries))


def test_mercadolibre_search_reuses_bounded_signal_plan():
    identity = ProductIdentity(
        brand="ExampleBrand", model="Model 123", mpn="ABC/123", upc="036000291452"
    )
    queries = _mercadolibre_queries(identity)
    assert queries[0] == "ABC/123"
    assert "ABC123" in queries
    assert "ABC-123" in queries
    assert "036000291452" in queries
    assert "ExampleBrand Model 123" in queries
    assert len(queries) <= 12
