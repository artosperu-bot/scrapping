from product_intelligence import discovery, price_peru_coverage, price_workflow
from product_intelligence.models import ProductIdentity


def _identity():
    return ProductIdentity(brand="ExampleBrand", model="Model 123", mpn="ABC/123")


def test_search_web_query_reports_raw_and_valid_counts_before_return(monkeypatch):
    raw = [
        ("https://shop.example.pe/product/a", "ExampleBrand Model 123 ABC/123", ""),
        ("https://other.pe/product/b", "ExampleBrand Model 123 ABC/123", ""),
    ]
    monkeypatch.setattr(discovery, "_provider_search", lambda *_a, **_k: raw)
    metrics = []
    urls = discovery.search_web_query(
        _identity(), '"ABC/123" site:shop.example.pe', limit=5,
        required_domain="shop.example.pe", on_metrics=metrics.append,
    )
    assert urls == ["https://shop.example.pe/product/a"]
    assert metrics == [{
        "query": '"ABC/123" site:shop.example.pe',
        "raw_results": 2,
        "domain_results": 1,
        "valid_results": 1,
    }]


def test_directed_alias_queries_emit_novelty_gain_until_plan_or_domain_budget(monkeypatch):
    events = []
    mapping = {
        '"ABC/123" site:shop.example.pe': ["https://shop.example.pe/product/a"],
        '"ABC123" site:shop.example.pe': [
            "https://shop.example.pe/product/b",
            "https://shop.example.pe/product/c",
        ],
    }

    def fake_search(_identity, query, **kwargs):
        rows = mapping.get(query, [])
        callback = kwargs.get("on_metrics")
        if callback:
            callback({"query": query, "raw_results": len(rows), "domain_results": len(rows), "valid_results": len(rows)})
        return rows

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)
    rows = price_peru_coverage._discover_target_domain(
        _identity(), "shop.example.pe", 5, on_query_event=events.append,
    )
    assert rows[:3] == [
        "https://shop.example.pe/product/a",
        "https://shop.example.pe/product/b",
        "https://shop.example.pe/product/c",
    ]
    exact = next(row for row in events if row["query"] == '"ABC/123" site:shop.example.pe')
    compact = next(row for row in events if row["query"] == '"ABC123" site:shop.example.pe')
    assert exact["signal_type"] == "MPN_ORIGINAL"
    assert exact["new_urls"] == 1
    assert exact["new_pdps"] == 1
    assert compact["signal_type"] == "MPN_COMPACT"
    assert compact["new_urls"] == 2
    assert compact["new_pdps"] == 2
    assert all("stop_reason" in row for row in events)


def test_mercadolibre_query_events_report_publication_and_seller_gain(monkeypatch):
    payload = {
        "results": [{
            "id": "MPE111",
            "title": "ExampleBrand Model 123 ABC/123",
            "price": 499,
            "currency_id": "PEN",
            "available_quantity": 2,
            "condition": "new",
            "permalink": "https://articulo.mercadolibre.com.pe/MPE-111",
            "seller": {"id": 1, "nickname": "Seller A"},
            "attributes": [
                {"id": "MPN", "value_name": "ABC/123"},
                {"id": "BRAND", "value_name": "ExampleBrand"},
                {"id": "MODEL", "value_name": "Model 123"},
            ],
        }]
    }

    class Response:
        status_code = 200
        def raise_for_status(self): return None
        def json(self): return payload

    class Client:
        def get(self, *_a, **_k): return Response()

    monkeypatch.setattr(price_workflow, "build_mercadolibre_api_client", lambda **_k: Client())
    monkeypatch.setattr(price_workflow, "_mercadolibre_queries", lambda _identity: ["ABC/123"])
    events = []
    rows = price_workflow._try_mercadolibre(_identity(), on_query_event=events.append)
    assert rows
    assert events[0]["query"] == "ABC/123"
    assert events[0]["raw_results"] == 1
    assert events[0]["valid_results"] == 1
    assert events[0]["new_listings"] == 1
    assert events[0]["new_sellers"] == 1
    assert events[0]["signal_type"] == "MPN_ORIGINAL"
