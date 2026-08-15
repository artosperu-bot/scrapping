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
