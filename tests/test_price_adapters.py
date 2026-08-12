from product_intelligence.models import ProductIdentity
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
