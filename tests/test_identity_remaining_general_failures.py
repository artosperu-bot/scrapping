from product_intelligence.discovery import SearchCandidate
from product_intelligence.identity_bootstrap import (
    build_discovery_fallback_queries,
    resolve_identity_from_candidates,
)
from product_intelligence.models import ProductIdentity


def c(url: str, title: str, snippet: str = ""):
    return SearchCandidate(url, title, snippet)


def test_ui_boilerplate_words_never_become_brand_candidates():
    identity = ProductIdentity(mpn="ZX-8100")
    candidates = [
        c("https://one.example/zx-8100", "Please visit ZX-8100", "Acme ZX-8100 product"),
        c("https://two.example/zx-8100", "Overview ZX-8100", "Acme ZX-8100 specifications"),
        c("https://three.example/zx-8100", "You can buy ZX-8100", "Manufacturer: Acme"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    forbidden = {"please", "please visit", "overview", "you", "you can", "this", "welcome", "featuring", "want"}
    assert not forbidden.intersection({k.lower() for k in result.brand_scores})


def test_brand_after_strong_identifier_can_be_learned_cross_source():
    identity = ProductIdentity(mpn="ZX-8101")
    candidates = [
        c("https://one.example/zx-8101", "ZX-8101 Acme Precision Mouse", "Acme peripheral"),
        c("https://two.example/zx-8101", "Product ZX-8101", "ZX-8101 Acme wireless mouse"),
        c("https://three.example/zx-8101", "ZX-8101 specifications", "Manufacturer: Acme"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"


def test_unstructured_family_suffix_does_not_replace_shorter_correlated_brand():
    identity = ProductIdentity(mpn="ZX-8102")
    candidates = [
        c("https://one.example/zx-8102", "Acme ProLine ZX-8102", "Acme ZX-8102 laptop"),
        c("https://two.example/zx-8102", "Acme ProLine ZX-8102 specifications", "Acme product"),
        c("https://three.example/zx-8102", "Acme ZX-8102", "Manufacturer: Acme"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    assert "Acme ProLine" not in result.brand_scores or result.brand_scores["Acme"] >= result.brand_scores["Acme ProLine"]


def test_zero_result_fallback_queries_include_generic_identifier_intents_without_brand_guessing():
    queries = build_discovery_fallback_queries("2Z609A")
    lower = [q.lower() for q in queries]
    assert any("part number" in q for q in lower)
    assert any("mpn" in q for q in lower)
    assert any("model" in q for q in lower)
    assert any("manual" in q or "datasheet" in q for q in lower)
    assert all("hp" not in q for q in lower)


def test_sibling_model_code_cannot_resolve_as_brand_from_serp_text():
    identity = ProductIdentity(mpn="AB12-CD34X")
    candidates = [
        c("https://one.example/ab12-cd34x", "Nova AB12-CD34X smartphone", "Compatible with AB12-CD34Y accessories"),
        c("https://two.example/ab12-cd34x", "AB12-CD34X Nova specifications", "Compare AB12-CD34X vs AB12-CD34Y"),
        c("https://three.example/ab12-cd34x", "Nova AB12-CD34X", "Manufacturer: Nova"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Nova"
    assert "AB12-CD34Y" not in result.brand_scores


def test_condition_words_before_brand_are_not_brand_candidates():
    identity = ProductIdentity(mpn="ZX-8110")
    candidates = [
        c("https://one.example/zx-8110", "Used Acme ZX-8110 Wireless Mouse", "Acme ZX-8110"),
        c("https://two.example/zx-8110", "Refurbished Acme ZX-8110", "Manufacturer: Acme"),
        c("https://three.example/zx-8110", "Renewed Acme ZX-8110", "Acme product ZX-8110"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    forbidden = {"used", "used acme", "refurbished", "refurbished acme", "renewed", "renewed acme"}
    assert not forbidden.intersection({k.lower() for k in result.brand_scores})


def test_generic_product_descriptors_cannot_win_as_brand_across_domains():
    identity = ProductIdentity(mpn="PR-4550")
    candidates = [
        c("https://one.example/pr-4550", "A4 multi-function printer PR-4550", "Acme PR-4550 printer"),
        c("https://two.example/pr-4550", "multi-function PR-4550 all-in-one", "Manufacturer: Acme"),
        c("https://three.example/pr-4550", "All-in-One PR-4550", "Acme PR-4550 specifications"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    forbidden = {"a4", "multi-function", "multifunction", "all-in-one"}
    assert not forbidden.intersection({k.lower() for k in result.brand_scores})
