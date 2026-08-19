from product_intelligence.price_identity import dedupe_offers
from product_intelligence.price_models import PriceOffer


def _offer(url: str, *, price: float = 518.0, seller: str = "Retailer Peru") -> PriceOffer:
    return PriceOffer(
        part_number="ABC/123",
        brand="ExampleBrand",
        model="Example Model",
        channel="Example Retailer",
        seller_display_name=seller,
        selling_price=price,
        currency="PEN",
        url=url,
        confidence=1.0,
        identity_match="EXACT_MPN",
        source_type="web",
        source_method="json_ld",
    )


def test_same_numeric_product_route_with_slug_aliases_dedupes_to_one_publication():
    offers = [
        _offer("https://retailer.pe/producto/5500-first-product-slug"),
        _offer("https://retailer.pe/producto/5500-second-product-slug"),
    ]

    deduped = dedupe_offers(offers)

    assert len(deduped) == 1


def test_different_numeric_product_routes_remain_distinct_publications():
    offers = [
        _offer("https://retailer.pe/producto/5500-first-product-slug"),
        _offer("https://retailer.pe/producto/5501-second-product-slug"),
    ]

    deduped = dedupe_offers(offers)

    assert len(deduped) == 2
