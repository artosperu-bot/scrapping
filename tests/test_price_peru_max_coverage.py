from product_intelligence.models import ProductIdentity
from product_intelligence import price_peru_coverage, price_workflow
from product_intelligence.price_adapters import parse_vtex_payload


IDENTITY = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")


def test_vtex_accepts_exact_mpn_from_item_reference_and_keeps_distinct_publications():
    payload = [
        {
            "productId": "1001",
            "productName": "Audifonos JBL Quantum 350 Wireless",
            "brand": "JBL",
            "link": "/oferta-a/p",
            "items": [{
                "itemId": "sku-a",
                "referenceId": [{"Key": "RefId", "Value": "JBLQ350WLBLKAM"}],
                "sellers": [{"sellerId": "pv", "sellerName": "Plaza Vea", "commertialOffer": {"Price": 469, "ListPrice": 499, "AvailableQuantity": 0}}],
            }],
        },
        {
            "productId": "1002",
            "productName": "Audifonos Gamer Quantum 350 Wireless",
            "brand": "JBL",
            "link": "/oferta-b/p",
            "items": [{
                "itemId": "sku-b",
                "referenceId": [{"Key": "RefId", "Value": "JBLQ350WLBLKAM"}],
                "sellers": [{"sellerId": "aliadas", "sellerName": "Marcas Aliadas", "commertialOffer": {"Price": 329, "ListPrice": 399, "AvailableQuantity": 2}}],
            }],
        },
    ]
    rows = parse_vtex_payload(payload, IDENTITY, channel="PlazaVea", source_url="https://www.plazavea.com.pe")
    assert {(r.publication_id, r.seller_display_name, r.selling_price) for r in rows} == {
        ("1001", "Plaza Vea", 469.0),
        ("1002", "Marcas Aliadas", 329.0),
    }


def test_targeted_discovery_covers_all_supported_peru_marketplaces(monkeypatch):
    expected_domains = {
        "falabella.com.pe",
        "simple.ripley.com.pe",
        "mercadolibre.com.pe",
        "plazavea.com.pe",
        "oechsle.pe",
        "sodimac.com.pe",
        "jbl.com.pe",
    }
    assert expected_domains.issubset(set(price_peru_coverage.PERU_MARKETPLACE_DOMAINS))

    seen_queries = []
    def fake_search(_identity, query, **_kwargs):
        seen_queries.append(query)
        return []
    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)
    price_peru_coverage.discover_additional_peru_pdps(IDENTITY, limit_per_domain=4)
    for domain in expected_domains:
        assert any(f"site:{domain}" in query for query in seen_queries), domain


def test_vtex_direct_probe_requests_wide_result_window(monkeypatch):
    captured = {}
    class Response:
        status_code = 200
        def json(self):
            return []
    def fake_get(url, **kwargs):
        captured["url"] = url
        return Response()
    monkeypatch.setattr(price_workflow.requests, "get", fake_get)
    price_workflow._try_vtex("https://www.plazavea.com.pe", IDENTITY, "PlazaVea")
    assert "_from=0" in captured["url"]
    assert "_to=49" in captured["url"]


def test_targeted_discovery_preserves_multiple_pdp_urls_from_same_marketplace(monkeypatch):
    urls = [
        "https://www.falabella.com.pe/falabella-pe/product/1/jblq350wlblkam/11",
        "https://www.falabella.com.pe/falabella-pe/product/2/jblq350wlblkam/22",
        "https://www.falabella.com.pe/falabella-pe/product/3/jblq350wlblkam/33",
    ]
    monkeypatch.setattr(
        price_peru_coverage,
        "search_web_query",
        lambda _identity, query, **_kwargs: urls if "falabella.com.pe" in query else [],
    )
    rows = price_peru_coverage.discover_additional_peru_pdps(
        IDENTITY,
        limit_per_domain=5,
        domains=("falabella.com.pe",),
    )
    assert rows == urls
