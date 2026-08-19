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


def test_vtex_exact_mpn_query_can_supply_identity_when_payload_hides_mpn_but_brand_and_discriminator_match():
    identity = ProductIdentity(brand="ExampleBrand", mpn="ABC-960G")
    payload = [
        {
            "productId": "RIGHT",
            "productName": "ExampleBrand Fast SSD 960GB",
            "brand": "ExampleBrand",
            "items": [{"itemId": "SKU-R", "name": "Fast SSD 960GB", "sellers": [
                {"sellerId": "seller-r", "sellerName": "Seller Right", "commertialOffer": {
                    "Price": 580, "ListPrice": 650, "AvailableQuantity": 5, "IsAvailable": True,
                }}
            ]}],
        },
        {
            "productId": "WRONG-BRAND",
            "productName": "OtherBrand Fast SSD 960GB",
            "brand": "OtherBrand",
            "items": [{"itemId": "SKU-B", "name": "Fast SSD 960GB", "sellers": [
                {"sellerId": "seller-b", "sellerName": "Seller Wrong", "commertialOffer": {
                    "Price": 400, "AvailableQuantity": 5, "IsAvailable": True,
                }}
            ]}],
        },
        {
            "productId": "WRONG-CAPACITY",
            "productName": "ExampleBrand Fast SSD 480GB",
            "brand": "ExampleBrand",
            "items": [{"itemId": "SKU-C", "name": "Fast SSD 480GB", "sellers": [
                {"sellerId": "seller-c", "sellerName": "Seller Wrong Capacity", "commertialOffer": {
                    "Price": 300, "AvailableQuantity": 5, "IsAvailable": True,
                }}
            ]}],
        },
    ]
    rows = parse_vtex_payload(
        payload,
        identity,
        channel="Example",
        source_url="https://shop.example.pe",
        retrieval_query="ABC-960G",
        retrieval_signal="MPN_ORIGINAL",
    )
    assert len(rows) == 1
    assert rows[0].publication_id == "RIGHT"
    assert rows[0].seller_display_name == "Seller Right"
    assert rows[0].selling_price == 580.0
    assert rows[0].identity_match == "EXACT_MPN"


def test_vtex_payload_without_retrieval_context_does_not_infer_missing_mpn_from_brand_capacity_alone():
    identity = ProductIdentity(brand="ExampleBrand", mpn="ABC-960G")
    payload = [{
        "productId": "RIGHT",
        "productName": "ExampleBrand Fast SSD 960GB",
        "brand": "ExampleBrand",
        "items": [{"itemId": "SKU-R", "name": "Fast SSD 960GB", "sellers": [
            {"sellerId": "seller-r", "sellerName": "Seller Right", "commertialOffer": {
                "Price": 580, "AvailableQuantity": 5, "IsAvailable": True,
            }}
        ]}],
    }]
    rows = parse_vtex_payload(payload, identity, channel="Example", source_url="https://shop.example.pe")
    assert rows == []


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
