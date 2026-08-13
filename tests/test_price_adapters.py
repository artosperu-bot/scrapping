from product_intelligence.models import ProductIdentity
from product_intelligence import price_adapters
from product_intelligence.price_adapters import parse_mercadolibre_payload, parse_vtex_payload


IDENTITY = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")


def test_parse_mercadolibre_payload_extracts_channel_seller_price():
    payload = {"results": [{"id": "MPE123", "title": "JBL Quantum 350 Wireless JBLQ350WLBLKAM", "price": 299, "original_price": 399, "available_quantity": 4, "condition": "new", "permalink": "https://mercadolibre.com.pe/p/MPE123", "seller": {"nickname": "QUEST TIME"}, "attributes": [{"id": "MODEL", "value_name": "JBLQ350WLBLKAM"}]}]}
    rows = parse_mercadolibre_payload(payload, IDENTITY)
    assert len(rows) == 1
    row = rows[0]
    assert row.channel == "MercadoLibre"
    assert row.seller_display_name == "QUEST TIME"
    assert row.selling_price == 299
    assert row.list_price == 399
    assert row.stock == 4
    assert row.confidence >= 0.9


def test_parse_vtex_payload_returns_one_offer_per_seller():
    payload = [{"productName": "JBL Quantum 350 Wireless", "productReference": "JBLQ350WLBLKAM", "items": [{"itemId": "1001", "sellers": [{"sellerId": "1", "sellerName": "Falabella", "commertialOffer": {"Price": 329, "ListPrice": 399, "AvailableQuantity": 5}}, {"sellerId": "22", "sellerName": "technopshops", "commertialOffer": {"Price": 299, "ListPrice": 399, "AvailableQuantity": 2}}]}]}]
    rows = parse_vtex_payload(payload, IDENTITY, channel="Falabella", source_url="https://falabella.example/search")
    assert [r.seller_display_name for r in rows] == ["Falabella", "technopshops"]
    assert [r.selling_price for r in rows] == [329, 299]
    assert all(r.channel == "Falabella" for r in rows)


def test_shopify_adapter_accepts_exact_sku_and_converts_cents():
    parser = getattr(price_adapters, "parse_shopify_product_payload", None)
    assert callable(parser), "Shopify structured adapter is required"
    payload = {
        "id": 9016,
        "title": "JBL Quantum 350 Wireless",
        "vendor": "JBL",
        "handle": "jbl-quantum-350-wireless",
        "variants": [{
            "id": 11,
            "sku": "JBLQ350WLBLKAM",
            "barcode": "050036382366",
            "price": 35500,
            "compare_at_price": 39500,
            "available": True,
        }],
    }
    rows = parser(
        payload, IDENTITY, channel="Arteus",
        source_url="https://arteus.pe/products/jbl-quantum-350-wireless",
    )
    assert len(rows) == 1
    assert rows[0].selling_price == 355.0
    assert rows[0].list_price == 395.0
    assert rows[0].source_method == "shopify_product_json"
    assert rows[0].identity_match == "EXACT_MPN"
