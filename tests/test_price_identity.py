from product_intelligence.models import ProductIdentity
from product_intelligence import price_identity
from product_intelligence.price_identity import dedupe_offers, score_offer_identity
from product_intelligence.price_models import PriceOffer, format_money


def identity():
    return ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM", ean="6925281993226")


def offer(channel, seller, price, url, source_type="structured", source_method="jsonld", publication_id=None):
    return PriceOffer(
        part_number="JBLQ350WLBLKAM", brand="JBL", model="Quantum 350 Wireless",
        channel=channel, seller_display_name=seller, selling_price=price,
        currency="PEN", url=url, confidence=1.0, identity_match="EXACT_MPN",
        source_type=source_type, source_method=source_method, publication_id=publication_id,
    )


def test_exact_mpn_is_max_confidence():
    score, match, conflicts = score_offer_identity(identity(), {"mpn": "JBLQ350WLBLKAM", "brand": "JBL"})
    assert score == 1.0
    assert match == "EXACT_MPN"
    assert conflicts == []


def test_exact_gtin_is_high_confidence():
    score, match, _ = score_offer_identity(identity(), {"gtin": "6925281993226", "brand": "JBL"})
    assert score >= 0.97
    assert match == "EXACT_GTIN"


def test_brand_and_full_model_can_match_without_mpn():
    score, match, conflicts = score_offer_identity(identity(), {"brand": "JBL", "model": "JBL Quantum 350 Wireless"})
    assert score >= 0.88
    assert match == "BRAND_MODEL"
    assert conflicts == []


def test_conflicting_generation_rejects_offer():
    score, match, conflicts = score_offer_identity(identity(), {"brand": "JBL", "model": "Quantum 360 Wireless"})
    assert score < 0.70
    assert match == "CONFLICT"
    assert conflicts


def test_dedupe_keeps_best_same_channel_seller_url():
    base = dict(part_number="JBLQ350WLBLKAM", brand="JBL", model="Quantum 350 Wireless", channel="Falabella", seller_display_name="technopshops", selling_price=299.0, currency="PEN", url="https://example.com/p/1")
    low = PriceOffer(**base, confidence=0.90, identity_match="BRAND_MODEL", source_type="web", source_method="html")
    high = PriceOffer(**base, confidence=1.0, identity_match="EXACT_MPN", source_type="api", source_method="json")
    rows = dedupe_offers([low, high])
    assert len(rows) == 1
    assert rows[0].confidence == 1.0
    assert rows[0].source_type == "api"


def test_money_format_respects_currency():
    assert format_money(299, "PEN") == "S/ 299.00"
    assert format_money(29936, "CLP") == "CLP 29,936"
    assert format_money(49.9, "USD") == "US$ 49.90"
    assert format_money(None, "PEN") == ""


def test_bigmarket_pen_offer_is_recognized_as_peru_market():
    row = offer(
        "Big Market", "Big Market", 479,
        "https://bigmarketperu.com/productos/audifonos-gamer-jbl-quantum-350-wireless",
    )
    assert price_identity.is_peru_offer(row)


def test_market_outlier_filter_rejects_absurd_price_but_keeps_real_range():
    fn = getattr(price_identity, "filter_market_outliers", None)
    assert callable(fn), "market outlier filter is required"
    prices = [233.50, 276.90, 299, 349, 355, 359, 399, 399, 479, 4.99]
    rows = [offer(f"Store{i}", f"Seller{i}", p, f"https://store{i}.com.pe/p") for i, p in enumerate(prices)]
    kept, rejected = fn(rows)
    assert [r.selling_price for r in rejected] == [4.99]
    assert {r.selling_price for r in kept} >= {233.50, 276.90, 299, 349, 355, 359, 399, 479}


def test_same_real_seller_has_same_competitor_key_across_channels():
    fn = getattr(price_identity, "competitor_key", None)
    assert callable(fn), "seller competitor identity is required"
    falabella = offer("Falabella", "TECHNOSHOPS PERU S.A.C.", 299, "https://falabella.com.pe/product/1")
    ripley = offer("Ripley", "TECHNOSHOPS PERU S.A.C.", 299, "https://simple.ripley.com.pe/pmp1")
    assert fn(falabella) == fn(ripley)


def test_dedupe_prefers_api_over_structured_representation_of_same_url():
    url = "https://arteus.pe/products/jbl-quantum-350-wireless"
    jsonld = offer("Arteus", None, 355, url, "structured", "jsonld")
    api = offer("Arteus", "Arteus", 355, url, "api", "shopify_product_json", "9016")
    rows = dedupe_offers([jsonld, api])
    assert len(rows) == 1
    assert rows[0].source_type == "api"
