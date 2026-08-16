from product_intelligence.discovery import SearchCandidate
from product_intelligence.identity_bootstrap import resolve_identity_from_candidates
from product_intelligence.models import ProductIdentity


def test_marketplace_titles_cannot_become_brand_without_explicit_brand_evidence():
    identity = ProductIdentity(mpn="ZX-8800")
    candidates = [
        SearchCandidate("https://amazon.com/dp/zx-8800", "Amazon ZX-8800", "ZX-8800 listing"),
        SearchCandidate("https://amazon.ca/dp/zx-8800", "Amazon ZX-8800", "ZX-8800 listing"),
        SearchCandidate("https://one.example/zx-8800", "Acme ZX-8800 Sensor", "Acme ZX-8800"),
        SearchCandidate("https://two.example/zx-8800", "ZX-8800 industrial sensor", "Manufacturer: Acme"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    assert "Amazon" not in result.brand_scores


def test_numeric_product_descriptor_does_not_extend_brand_name():
    identity = ProductIdentity(mpn="ZX-8801")
    candidates = [
        SearchCandidate("https://one.example/zx-8801", "Acme 240W Charge Cable ZX-8801", "Acme ZX-8801 cable"),
        SearchCandidate("https://two.example/zx-8801", "Acme 240W ZX-8801", "Brand: Acme"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    assert "Acme 240W" not in result.brand_scores


def test_brand_can_be_learned_from_snippet_when_title_is_retailer_led():
    identity = ProductIdentity(mpn="ZX-8802")
    candidates = [
        SearchCandidate("https://one.example/zx-8802", "ZX-8802 available now", "Acme ZX-8802 industrial sensor"),
        SearchCandidate("https://two.example/zx-8802", "ZX-8802 specifications", "Acme ZX-8802 product details"),
        SearchCandidate("https://three.example/zx-8802", "ZX-8802 datasheet", "Manufacturer: Acme"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    assert result.brand_hosts["Acme"] >= 2


def test_three_independent_hosts_can_resolve_brand_over_single_host_noise():
    identity = ProductIdentity(mpn="ZX-8803")
    candidates = [
        SearchCandidate("https://one.example/zx-8803", "Acme ZX-8803", "Acme product"),
        SearchCandidate("https://two.example/zx-8803", "ZX-8803", "Acme ZX-8803 specifications"),
        SearchCandidate("https://three.example/zx-8803", "ZX-8803", "Acme ZX-8803 datasheet"),
        SearchCandidate("https://publisher.example/zx-8803", "Publisher ZX-8803", "ZX-8803 details"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"


def test_two_word_alphabetic_brand_is_kept_but_model_suffix_is_not():
    identity = ProductIdentity(mpn="ZX-8804")
    candidates = [
        SearchCandidate("https://one.example/zx-8804", "Western Digital Blue ZX-8804", "Western Digital ZX-8804"),
        SearchCandidate("https://two.example/zx-8804", "Western Digital ZX-8804", "Manufacturer: Western Digital"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Western Digital"
    assert "Western Digital Blue" not in result.brand_scores
