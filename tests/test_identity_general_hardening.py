from product_intelligence.discovery import SearchCandidate
from product_intelligence.identity_bootstrap import (
    PageIdentitySignal,
    resolve_identity_from_candidates,
    resolve_identity_with_page_signals,
)
from product_intelligence.models import ProductIdentity


def c(url: str, title: str, snippet: str = ""):
    return SearchCandidate(url, title, snippet)


def test_hyphenated_generic_descriptors_never_survive_as_brand_scores():
    identity = ProductIdentity(mpn="PR-4550")
    candidates = [
        c("https://one.example/pr-4550", "A4 multi-function printer PR-4550", "Acme PR-4550 printer"),
        c("https://two.example/pr-4550", "multi-function PR-4550 all-in-one", "Manufacturer: Acme"),
        c("https://three.example/pr-4550", "All-in-One PR-4550", "Acme PR-4550 specifications"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    forbidden = {"a4", "multi-function", "multifunction", "all-in-one", "allinone"}
    assert not forbidden.intersection({k.lower() for k in result.brand_scores})


def test_cross_domain_leading_brand_can_use_retail_as_weak_discovery_evidence():
    identity = ProductIdentity(mpn="ZX-9911")
    candidates = [
        c("https://www.amazon.com/dp/ZX-9911", "ExampleTech Nova Mouse", "ExampleTech ZX-9911 wireless mouse"),
        c("https://www.ebay.com/itm/ZX-9911", "ExampleTech Nova Mouse ZX-9911", "new product"),
        c("https://catalog.example.org/zx-9911", "ExampleTech Nova Mouse", "MPN ZX-9911. Manufacturer: ExampleTech"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "ExampleTech"


def test_two_word_brand_is_not_truncated_when_full_phrase_has_equal_independent_support():
    identity = ProductIdentity(mpn="NS-8844")
    candidates = [
        c("https://one.example/ns-8844", "North Star NS-8844 SSD", "North Star storage"),
        c("https://two.example/ns-8844", "North Star NS-8844 specifications", "solid state drive"),
        c("https://three.example/ns-8844", "North Star NS-8844", "Manufacturer: North Star"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "North Star"


def test_short_brand_still_wins_when_it_has_broader_support_than_two_word_family_phrase():
    identity = ProductIdentity(mpn="ZX-8102")
    candidates = [
        c("https://one.example/zx-8102", "Acme ProLine ZX-8102", "Acme ZX-8102 laptop"),
        c("https://two.example/zx-8102", "Acme ProLine ZX-8102 specifications", "Acme product"),
        c("https://three.example/zx-8102", "Acme ZX-8102", "Manufacturer: Acme"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"


def test_exact_page_backed_brand_outweighs_cross_domain_product_family_noise():
    identity = ProductIdentity(mpn="PR-9900")
    candidates = [
        c("https://one.example/pr-9900", "LaserFamily PR-9900 printer", "Acme PR-9900"),
        c("https://two.example/pr-9900", "LaserFamily PR-9900 specifications", "printer family"),
        c("https://three.example/pr-9900", "Acme PR-9900", "technical specifications"),
    ]
    page_signals = [
        PageIdentitySignal(
            url="https://manufacturer.example/pr-9900",
            brand="Acme",
            model="PR-9900",
            exact_raw_match=True,
            strong_identifier_match=True,
            material=True,
            structured_brand=True,
            authority_owned=True,
            reason="OK",
        )
    ]
    result = resolve_identity_with_page_signals(identity, candidates, page_signals)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"


def test_sibling_identifier_remains_rejected_as_brand():
    identity = ProductIdentity(mpn="2312DRA50G")
    candidates = [
        c("https://one.example/p", "2312DRA50I 2312DRA50G smartphone", "ExampleTech device"),
        c("https://two.example/p", "2312DRA50I 2312DRA50G", "Manufacturer: ExampleTech"),
        c("https://three.example/p", "ExampleTech 2312DRA50G", "product"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.identity.brand != "2312DRA50I"
