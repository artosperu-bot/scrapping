from product_intelligence.models import ProductIdentity
from product_intelligence.price_adapters import parse_mercadolibre_payload, parse_vtex_payload
from product_intelligence.price_discovery import extract_page_offers


def _identity():
    return ProductIdentity(brand="ExampleBrand", model="Model 123", mpn="ABC/123")


def test_mercadolibre_catalog_search_preserves_multiple_publications_and_sellers():
    payload = {
        "results": [
            {
                "id": "MPE111",
                "title": "ExampleBrand Model 123 ABC/123",
                "price": 499,
                "original_price": 549,
                "currency_id": "PEN",
                "available_quantity": 5,
                "condition": "new",
                "permalink": "https://articulo.mercadolibre.com.pe/MPE-111",
                "seller": {"id": 1, "nickname": "Seller A"},
                "attributes": [
                    {"id": "MPN", "value_name": "ABC/123"},
                    {"id": "BRAND", "value_name": "ExampleBrand"},
                    {"id": "MODEL", "value_name": "Model 123"},
                ],
            },
            {
                "id": "MPE222",
                "title": "ExampleBrand Model 123 ABC/123",
                "price": 505,
                "currency_id": "PEN",
                "available_quantity": 2,
                "condition": "new",
                "permalink": "https://articulo.mercadolibre.com.pe/MPE-222",
                "seller": {"id": 2, "nickname": "Seller B"},
                "attributes": [
                    {"id": "MPN", "value_name": "ABC/123"},
                    {"id": "BRAND", "value_name": "ExampleBrand"},
                    {"id": "MODEL", "value_name": "Model 123"},
                ],
            },
        ]
    }
    rows = parse_mercadolibre_payload(payload, _identity())
    assert len(rows) == 2
    assert {row.publication_id for row in rows} == {"MPE111", "MPE222"}
    assert {row.seller_display_name for row in rows} == {"Seller A", "Seller B"}
    assert {row.selling_price for row in rows} == {499.0, 505.0}


def test_vtex_catalog_item_preserves_multiple_marketplace_sellers():
    payload = [{
        "productId": "CAT-1",
        "productName": "ExampleBrand Model 123 ABC/123",
        "brand": "ExampleBrand",
        "items": [{
            "itemId": "SKU-1",
            "name": "ABC/123",
            "referenceId": [{"Value": "ABC/123"}],
            "sellers": [
                {"sellerId": "seller-a", "sellerName": "Seller A", "commertialOffer": {
                    "Price": 499, "ListPrice": 549, "AvailableQuantity": 4, "IsAvailable": True,
                }},
                {"sellerId": "seller-b", "sellerName": "Seller B", "commertialOffer": {
                    "Price": 505, "ListPrice": 559, "AvailableQuantity": 1, "IsAvailable": True,
                }},
            ],
        }],
    }]
    for channel in ("Falabella", "PlazaVea"):
        rows = parse_vtex_payload(payload, _identity(), channel=channel, source_url="https://shop.example.pe")
        assert len(rows) == 2
        assert {row.seller_display_name for row in rows} == {"Seller A", "Seller B"}
        assert all(row.publication_id == "CAT-1" for row in rows)


def test_structured_product_offers_preserve_multiple_sellers_for_blockable_marketplaces():
    html = '''
    <html><head><title>ExampleBrand Model 123 ABC/123</title>
    <script type="application/ld+json">
    {
      "@context":"https://schema.org",
      "@type":"Product",
      "name":"ExampleBrand Model 123 ABC/123",
      "mpn":"ABC/123",
      "brand":{"@type":"Brand","name":"ExampleBrand"},
      "model":"Model 123",
      "offers":[
        {"@type":"Offer","price":"499","priceCurrency":"PEN","url":"/offer-a","seller":{"@type":"Organization","name":"Seller A"}},
        {"@type":"Offer","price":"505","priceCurrency":"PEN","url":"/offer-b","seller":{"@type":"Organization","name":"Seller B"}}
      ]
    }
    </script></head><body><h1>ExampleBrand Model 123 ABC/123</h1></body></html>
    '''
    cases = [
        ("https://simple.ripley.com.pe/example-abc123-pmp00001", "Ripley"),
        ("https://www.sodimac.com.pe/sodimac-pe/articulo/1/example", "Sodimac"),
    ]
    for url, channel in cases:
        rows = extract_page_offers(html, url, _identity(), channel=channel)
        assert len(rows) == 2
        assert {row.seller_display_name for row in rows} == {"Seller A", "Seller B"}
        assert {row.selling_price for row in rows} == {499.0, 505.0}
