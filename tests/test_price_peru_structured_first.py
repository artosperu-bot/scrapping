from __future__ import annotations

from product_intelligence.models import ProductIdentity
from product_intelligence.price_adapters import parse_vtex_payload
from product_intelligence import price_workflow


PLAZAVEA_EXACT_PAYLOAD = [
    {
        "productId": "100488604",
        "productName": "Audífonos Over Ear JBL JBLQ350WLBLKAM Negro",
        "brand": "JBL",
        "productReference": "20283591",
        "link": "https://www.plazavea.com.pe/audifonos-over-ear-jbl-jblq350wlblkam-negro/p",
        "Modelo": ["JBLQ350WLBLKAM"],
        "items": [
            {
                "itemId": "10696064",
                "ean": "6925281986505",
                "sellers": [
                    {
                        "sellerId": "1",
                        "sellerName": "Plaza Vea",
                        "commertialOffer": {
                            "Price": 469.0,
                            "ListPrice": 469.0,
                            "AvailableQuantity": 0,
                            "IsAvailable": False,
                        },
                    }
                ],
            }
        ],
    }
]


def _identity() -> ProductIdentity:
    return ProductIdentity(brand="JBL", model="JBLQ350WLBLKAM", mpn="JBLQ350WLBLKAM")


def test_vtex_parser_prefers_exact_product_link_and_keeps_out_of_stock_price():
    rows = parse_vtex_payload(
        PLAZAVEA_EXACT_PAYLOAD,
        _identity(),
        channel="PlazaVea",
        source_url="https://www.plazavea.com.pe",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.channel == "PlazaVea"
    assert row.seller_display_name == "Plaza Vea"
    assert row.selling_price == 469.0
    assert row.stock == 0
    assert row.availability == "unavailable"
    assert row.url == "https://www.plazavea.com.pe/audifonos-over-ear-jbl-jblq350wlblkam-negro/p"
    assert row.confidence >= 0.95


def test_run_price_product_probes_peru_structured_sources_even_when_web_discovery_is_empty(monkeypatch, tmp_path):
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return PLAZAVEA_EXACT_PAYLOAD

    requested = []

    def fake_get(url, **_kwargs):
        requested.append(url)
        return Response()

    monkeypatch.setattr(price_workflow.requests, "get", fake_get)
    monkeypatch.setattr(price_workflow, "_try_mercadolibre", lambda _identity: [])
    monkeypatch.setattr(price_workflow, "discover_price_sources", lambda _identity, limit=12: [])
    monkeypatch.setattr(
        price_workflow,
        "PERU_STRUCTURED_SOURCES",
        (("PlazaVea", "https://www.plazavea.com.pe"),),
        raising=False,
    )

    rows = price_workflow.run_price_product(_identity(), tmp_path)

    assert any("plazavea.com.pe/api/catalog_system/pub/products/search" in url for url in requested)
    assert len(rows) == 1
    assert rows[0].channel == "PlazaVea"
    assert rows[0].selling_price == 469.0
    assert rows[0].currency == "PEN"
