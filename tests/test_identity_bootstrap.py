from product_intelligence.discovery import SearchCandidate
from product_intelligence.identity_bootstrap import (
    build_bootstrap_queries,
    build_deep_queries,
    resolve_identity_from_candidates,
)
from product_intelligence.models import ProductIdentity


def test_unknown_product_name_discovers_brand_without_hardcoding():
    identity = ProductIdentity(product_name="Armor 22")
    candidates = [
        SearchCandidate(
            "https://www.ulefone.com/products/armor-22",
            "Ulefone Armor 22 Rugged Smartphone",
            "Official Ulefone Armor 22 product specifications",
        ),
        SearchCandidate(
            "https://www.gsmarena.example/ulefone-armor-22",
            "Ulefone Armor 22 specifications",
            "Ulefone Armor 22 rugged phone",
        ),
        SearchCandidate(
            "https://retailer.example/armor-22",
            "Ulefone Armor 22 8GB 256GB",
            "Brand Ulefone; model Armor 22",
        ),
    ]

    result = resolve_identity_from_candidates(identity, candidates)

    assert result.status == "RESOLVED"
    assert result.identity.brand == "Ulefone"
    assert result.identity.model == "Armor 22"
    assert result.confidence >= 0.75
    assert result.hardcoded is False


def test_unknown_strong_identifier_keeps_identifier_and_discovers_brand():
    identity = ProductIdentity(mpn="ZX-4109")
    candidates = [
        SearchCandidate(
            "https://www.acme.example/products/zx-4109",
            "Acme Industrial ZX-4109 Sensor",
            "Official product page for Acme ZX-4109",
        ),
        SearchCandidate(
            "https://distributor.example/acme-zx-4109",
            "Acme ZX-4109 technical specifications",
            "Manufacturer: Acme",
        ),
    ]

    result = resolve_identity_from_candidates(identity, candidates)

    assert result.status == "RESOLVED"
    assert result.identity.mpn == "ZX-4109"
    assert result.identity.brand == "Acme"
    assert result.identity.model is None


def test_conflicting_brand_candidates_remain_unresolved():
    identity = ProductIdentity(mpn="ZX-4109")
    candidates = [
        SearchCandidate("https://one.example/zx-4109", "Acme ZX-4109 Sensor", "Brand: Acme"),
        SearchCandidate("https://two.example/zx-4109", "Nova ZX-4109 Sensor", "Brand: Nova"),
    ]

    result = resolve_identity_from_candidates(identity, candidates)

    assert result.status == "IDENTITY_UNRESOLVED"
    assert result.identity.brand is None
    assert result.reason in {"AMBIGUOUS_BRAND", "INSUFFICIENT_EVIDENCE"}


def test_bootstrap_queries_do_not_invent_brand_before_resolution():
    identity = ProductIdentity(product_name="Armor 22")
    queries = build_bootstrap_queries(identity)

    assert queries[0] == '"Armor 22"'
    assert all("Ulefone" not in q for q in queries)
    assert any("specifications" in q for q in queries)


def test_deep_queries_use_brand_only_after_it_is_resolved():
    identity = ProductIdentity(brand="Acme", mpn="ZX-4109")
    queries = build_deep_queries(identity, official_domain_hint="acme.example")

    assert any('"ZX-4109" "Acme"' in q for q in queries)
    assert any('site:acme.example "ZX-4109"' in q for q in queries)
    assert any("pdf" in q.lower() for q in queries)
