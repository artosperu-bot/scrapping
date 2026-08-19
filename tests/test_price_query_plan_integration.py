from product_intelligence import price_peru_coverage
from product_intelligence.models import ProductIdentity
from product_intelligence.price_peru_coverage import _general_retail_queries, _queries
from product_intelligence.price_workflow import _mercadolibre_queries


def test_directed_domain_queries_use_mpn_separator_aliases():
    identity = ProductIdentity(brand="ExampleBrand", model="Model 123", mpn="ABC/123")
    queries = _queries(identity, "shop.example.pe")
    assert any('\"ABC/123\" site:shop.example.pe' == q for q in queries)
    assert any('\"ABC123\" site:shop.example.pe' == q for q in queries)
    assert any('\"ABC-123\" site:shop.example.pe' == q for q in queries)
    assert any('\"ABC 123\" site:shop.example.pe' == q for q in queries)


def test_directed_discovery_keeps_alias_novelty_after_exact_pdp(monkeypatch):
    identity = ProductIdentity(brand="ExampleBrand", model="Model 123", mpn="ABC/123")
    exact = "https://shop.example.pe/product/listing-a"
    compact_b = "https://shop.example.pe/product/listing-b"
    compact_c = "https://shop.example.pe/product/listing-c"
    calls = []

    def fake_search(_identity, query, **kwargs):
        calls.append((query, kwargs.get("required_domain")))
        if query == '\"ABC/123\" site:shop.example.pe':
            return [exact]
        if query == '\"ABC123\" site:shop.example.pe':
            return [compact_b, compact_c]
        return []

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)
    rows = price_peru_coverage._discover_target_domain(identity, "shop.example.pe", 5)

    assert rows == [exact, compact_b, compact_c]
    assert ('\"ABC/123\" site:shop.example.pe', "shop.example.pe") in calls
    assert ('\"ABC123\" site:shop.example.pe', "shop.example.pe") in calls


def test_open_peru_queries_include_verified_barcode_and_brand_model_without_case_noise():
    identity = ProductIdentity(
        brand="ExampleBrand", model="Model 123", mpn="ABC/123", upc="036000291452"
    )
    queries = _general_retail_queries(identity)
    joined = "\n".join(queries)
    assert '\"ABC123\" precio Perú' in joined
    assert '\"036000291452\" precio Perú' in joined
    assert '\"Model 123\"' in joined
    assert len(queries) == len(set(q.casefold() for q in queries))


def test_open_peru_queries_include_country_scope_for_source_discovery():
    queries = _general_retail_queries(ProductIdentity(mpn="ABC/123"))
    assert '\"ABC/123\" site:.pe' in queries
    assert '\"ABC/123\" site:.com.pe' in queries


def test_country_scope_site_query_is_not_treated_as_one_literal_host():
    assert price_peru_coverage._required_domain_from_query('\"ABC/123\" site:.pe') is None
    assert price_peru_coverage._required_domain_from_query('\"ABC/123\" site:.com.pe') is None
    assert price_peru_coverage._required_domain_from_query('\"ABC/123\" site:shop.example.pe') == "shop.example.pe"


def test_country_scope_query_reaches_search_without_fake_required_host(monkeypatch):
    identity = ProductIdentity(mpn="ABC/123")
    calls = []

    def fake_search(_identity, query, **kwargs):
        calls.append((query, kwargs.get("required_domain")))
        return ["https://retailer.pe/product/abc123"]

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)
    price_peru_coverage._search_query_specs(
        identity,
        [('\"ABC/123\" site:.pe', "PERU_TLD_SCOPE")],
        5,
    )

    assert calls == [('\"ABC/123\" site:.pe', None)]


def test_country_scope_diversity_query_excludes_seen_domains():
    query = price_peru_coverage._country_scope_diversity_query(
        "ABC/123", {"first.pe", "second.com.pe"}, round_index=0
    )
    assert query.startswith('\"ABC/123\" site:.pe')
    assert "-site:first.pe" in query
    assert "-site:second.com.pe" in query


def test_open_peru_diversity_lane_surfaces_new_domain_after_initial_plateau(monkeypatch):
    identity = ProductIdentity(mpn="ABC/123")
    events = []
    calls = []

    monkeypatch.setattr(
        price_peru_coverage,
        "_general_retail_query_specs",
        lambda *_args, **_kwargs: [('\"ABC/123\" precio Perú', "MPN_ORIGINAL")],
    )
    monkeypatch.setattr(
        price_peru_coverage,
        "_search_query_specs",
        lambda *_args, **_kwargs: [
            (
                '\"ABC/123\" precio Perú',
                "MPN_ORIGINAL",
                ["https://first.pe/product/abc123"],
                {"raw_results": 1, "valid_results": 1},
            )
        ],
    )

    def fake_search(_identity, query, **kwargs):
        calls.append(query)
        if "-site:first.pe" in query:
            return ["https://second.pe/product/abc123"], {
                "query": query,
                "raw_results": 1,
                "valid_results": 1,
            }
        return [], {"query": query, "raw_results": 0, "valid_results": 0}

    monkeypatch.setattr(price_peru_coverage, "_search_with_metrics", fake_search)
    rows = price_peru_coverage.discover_general_peru_retailers(
        identity, limit=5, on_query_event=events.append
    )

    assert "https://first.pe/product/abc123" in rows
    assert "https://second.pe/product/abc123" in rows
    assert any("-site:first.pe" in query for query in calls)
    assert any(event.get("signal_type") == "PERU_TLD_DIVERSITY" for event in events)


def test_open_peru_site_queries_enforce_domain_before_ranking(monkeypatch):
    identity = ProductIdentity(mpn="ABC/123")
    calls = []

    def fake_search(_identity, query, **kwargs):
        calls.append((query, kwargs.get("required_domain")))
        return ["https://shop.example.pe/product/abc123"]

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)
    price_peru_coverage._search_query_specs(
        identity,
        [('\"ABC/123\" site:shop.example.pe', "KNOWN_DOMAIN_HINT")],
        5,
    )

    assert calls == [('\"ABC/123\" site:shop.example.pe', "shop.example.pe")]


def test_open_peru_site_queries_enforce_domain_without_telemetry(monkeypatch):
    identity = ProductIdentity(mpn="ABC/123")
    calls = []

    def fake_search(_identity, query, **kwargs):
        calls.append((query, kwargs.get("required_domain")))
        return ["https://shop.example.pe/product/abc123"]

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)
    rows = price_peru_coverage._search_query_batches(
        identity,
        ['\"ABC/123\" site:shop.example.pe'],
        5,
    )

    assert rows == [["https://shop.example.pe/product/abc123"]]
    assert calls == [('\"ABC/123\" site:shop.example.pe', "shop.example.pe")]


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
