from product_intelligence.discovery import SearchCandidate
from product_intelligence.identity_refinement import _select_brand, _select_model


def test_brand_refinement_prefers_short_repeated_brand_over_brand_plus_model_word():
    raw = "ACMEX100BLK"
    rows = [
        SearchCandidate("https://acme.com/products/acmex100blk", "Acme Nova X100 Wireless Headset ACMEX100BLK", ""),
        SearchCandidate("https://dealer.example/acmex100blk", "Acme Nova X100 Headset ACMEX100BLK", ""),
        SearchCandidate("https://specs.example/acmex100blk", "Acme Nova X100 specifications ACMEX100BLK", ""),
    ]
    brand, support, domain = _select_brand(rows, raw, "Acme Nova")
    assert brand.lower() == "acme"
    assert support >= 2
    assert domain == "acme.com"


def test_multiword_brand_can_win_when_host_corroborates_compact_brand():
    raw = "NS5100A"
    rows = [
        SearchCandidate("https://northstar.com/ns5100a", "North Star Vector 5100 NS5100A", ""),
        SearchCandidate("https://dealer.example/ns5100a", "North Star Vector 5100 NS5100A", ""),
    ]
    brand, support, domain = _select_brand(rows, raw, None)
    assert brand.lower() == "north star"
    assert support == 2
    assert domain == "northstar.com"


def test_model_refinement_uses_cross_domain_common_model_not_full_marketing_title():
    raw = "ACMEX100BLK"
    rows = [
        SearchCandidate("https://acme.com/acmex100blk", "Acme Nova X100 Wireless Gaming Headset ACMEX100BLK", ""),
        SearchCandidate("https://dealer.example/acmex100blk", "Acme Nova X100 Wireless Headphones ACMEX100BLK", ""),
        SearchCandidate("https://specs.example/acmex100blk", "Acme Nova X100 specifications ACMEX100BLK", ""),
    ]
    model, support = _select_model(rows, raw, "Acme")
    assert model is not None
    assert "nova" in model.lower()
    assert "x100" in model.lower()
    assert len(model.split()) <= 4
    assert support >= 2
