from product_intelligence.price_identity import is_peru_offer
from product_intelligence.price_models import PriceOffer


def _offer(url: str, *, currency: str = "PEN") -> PriceOffer:
    return PriceOffer(
        part_number="ABC/123",
        brand="ExampleBrand",
        model="Example Model",
        channel="Example Retailer",
        seller_display_name="Example Retailer",
        selling_price=499.0,
        currency=currency,
        url=url,
        confidence=1.0,
        identity_match="EXACT_MPN",
        source_type="web",
        source_method="json_ld",
    )


def test_peru_named_dotcom_pen_offer_is_recognized_as_peru_market():
    assert is_peru_offer(_offer("https://retailerperu.com/product/abc123"))


def test_generic_foreign_dotcom_pen_offer_stays_outside_peru_market():
    assert not is_peru_offer(_offer("https://retailerexample.com/product/abc123"))


def test_peru_named_dotcom_usd_offer_still_belongs_to_peru_market():
    assert is_peru_offer(_offer("https://retailerperu.com/product/abc123", currency="USD"))
