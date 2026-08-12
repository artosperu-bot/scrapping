from product_intelligence.models import ProductIdentity
from product_intelligence.price_identity import dedupe_offers, score_offer_identity
from product_intelligence.price_models import PriceOffer


def identity():
    return ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM", ean="6925281993226")


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
