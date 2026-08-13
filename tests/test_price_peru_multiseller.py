from types import SimpleNamespace

from product_intelligence.models import ProductIdentity
from product_intelligence.price_adapters import parse_vtex_payload
from product_intelligence.price_identity import score_offer_identity
from product_intelligence.price_models import PriceOffer
from product_intelligence import price_workflow


def _identity():
    return ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")


def _offer(*, channel: str, seller: str, price: float, url: str, publication_id: str = "p1"):
    return PriceOffer(
        part_number="JBLQ350WLBLKAM",
        brand="JBL",
        model="Quantum 350 Wireless",
        channel=channel,
        seller_display_name=seller,
        selling_price=price,
        currency="PEN",
        url=url,
        confidence=1.0,
        identity_match="EXACT_MPN",
        source_type="web",
        source_method="test",
        publication_id=publication_id,
    )


def test_structured_peru_probes_include_falabella_plazavea_and_oechsle():
    channels = {channel for channel, _ in price_workflow.PERU_STRUCTURED_SOURCES}
    assert {"Falabella", "PlazaVea", "Oechsle"}.issubset(channels)


def test_exact_mpn_is_rejected_when_observed_model_generation_conflicts():
    score, match, conflicts = score_offer_identity(
        _identity(),
        {
            "mpn": "JBLQ350WLBLKAM",
            "brand": "JBL",
            "model": "JBL Quantum 910X",
            "title": "JBL Quantum 910X Wireless Gaming Headset",
        },
    )
    assert score == 0.0
    assert match == "CONFLICT"
    assert "model_generation_conflict" in conflicts


def test_vtex_keeps_multiple_sellers_for_same_exact_product():
    payload = [
        {
            "productId": "100488604",
            "productName": "Audífonos Over Ear JBL JBLQ350WLBLKAM Negro",
            "brand": "JBL",
            "Modelo": ["JBLQ350WLBLKAM"],
            "link": "/audifonos-over-ear-jbl-jblq350wlblkam-negro/p",
            "items": [
                {
                    "itemId": "10696064",
                    "sellers": [
                        {
                            "sellerId": "1",
                            "sellerName": "Plaza Vea",
                            "commertialOffer": {"Price": 469, "ListPrice": 469, "AvailableQuantity": 0},
                        },
                        {
                            "sellerId": "marcas-aliadas",
                            "sellerName": "Marcas Aliadas",
                            "commertialOffer": {"Price": 399, "ListPrice": 499, "AvailableQuantity": 4},
                        },
                    ],
                }
            ],
        }
    ]
    rows = parse_vtex_payload(payload, _identity(), channel="PlazaVea", source_url="https://www.plazavea.com.pe")
    assert len(rows) == 2
    assert {row.seller_display_name for row in rows} == {"Plaza Vea", "Marcas Aliadas"}
    assert {row.selling_price for row in rows} == {469.0, 399.0}


def test_price_workflow_returns_only_peru_offers(monkeypatch, tmp_path):
    monkeypatch.setattr(price_workflow, "PERU_STRUCTURED_SOURCES", ())
    monkeypatch.setattr(price_workflow, "_try_mercadolibre", lambda identity: [])
    monkeypatch.setattr(price_workflow, "discover_price_sources", lambda identity, limit=12: ["https://shop.example.com/item"])
    monkeypatch.setattr(
        price_workflow,
        "fetch_page",
        lambda *args, **kwargs: SimpleNamespace(final_url="https://shop.example.com/item", html="<html></html>"),
    )
    monkeypatch.setattr(
        price_workflow,
        "extract_page_offers",
        lambda *args, **kwargs: [
            _offer(
                channel="International Shop",
                seller="Foreign Seller",
                price=100,
                url="https://shop.example.com/item",
            )
        ],
    )

    rows = price_workflow.run_price_product(_identity(), tmp_path)
    assert rows == []
