from product_intelligence.discovery import SearchCandidate
from product_intelligence.identity_bootstrap import (
    PageIdentitySignal,
    build_bootstrap_queries,
    build_context_queries,
    build_deep_queries,
    build_discovery_fallback_queries,
    derive_context_terms,
    filter_bootstrap_candidates,
    identity_probe_budget,
    resolve_identity_from_candidates,
    resolve_identity_with_page_signals,
)
from product_intelligence.models import ProductIdentity


def test_unknown_product_name_discovers_brand_without_hardcoding():
    identity = ProductIdentity(product_name="Armor 22")
    candidates = [
        SearchCandidate("https://www.ulefone.com/products/armor-22", "Ulefone Armor 22 Rugged Smartphone", "Official Ulefone Armor 22 product specifications"),
        SearchCandidate("https://www.gsmarena.example/ulefone-armor-22", "Ulefone Armor 22 specifications", "Ulefone Armor 22 rugged phone"),
        SearchCandidate("https://retailer.example/armor-22", "Ulefone Armor 22 8GB 256GB", "Brand Ulefone; model Armor 22"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Ulefone"
    assert result.identity.model == "Armor 22"
    assert result.confidence >= 0.75
    assert result.hardcoded is False
    assert result.official_domain_hint is None


def test_unknown_strong_identifier_keeps_identifier_and_discovers_brand():
    identity = ProductIdentity(mpn="ZX-4109")
    candidates = [
        SearchCandidate("https://www.acme.example/products/zx-4109", "Acme Industrial ZX-4109 Sensor", "Official product page for Acme ZX-4109"),
        SearchCandidate("https://distributor.example/acme-zx-4109", "Acme ZX-4109 technical specifications", "Manufacturer: Acme"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.mpn == "ZX-4109"
    assert result.identity.brand == "Acme"
    assert result.identity.model is None
    assert result.official_domain_hint is None


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


def test_same_host_duplicate_noise_cannot_outvote_cross_source_brand():
    identity = ProductIdentity(mpn="ZX-4109")
    candidates = [
        SearchCandidate("https://market.example/a/zx-4109", "Marketplace ZX-4109", "ZX-4109 listing"),
        SearchCandidate("https://market.example/b/zx-4109", "Marketplace ZX-4109", "ZX-4109 listing"),
        SearchCandidate("https://market.example/c/zx-4109", "Marketplace ZX-4109", "ZX-4109 listing"),
        SearchCandidate("https://one.example/zx-4109", "Acme ZX-4109 Sensor", "Acme ZX-4109"),
        SearchCandidate("https://two.example/acme-zx-4109", "Acme ZX-4109 specifications", "Manufacturer: Acme"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    assert result.brand_hosts["Acme"] == 2


def test_non_product_intent_noise_cannot_outvote_product_brand():
    identity = ProductIdentity(mpn="ZX-5000")
    candidates = [
        SearchCandidate("https://maker.example/zx-5000", "Acme ZX-5000 Sensor", "Acme ZX-5000 industrial sensor"),
        SearchCandidate("https://dealer.example/acme-zx-5000", "Acme ZX-5000 specifications", "Manufacturer: Acme"),
        SearchCandidate("https://flight-one.example/zx-5000", "AirlineCo ZX-5000 flight tracking", "Track airline flight ZX-5000"),
        SearchCandidate("https://flight-two.example/zx-5000", "AirlineCo ZX-5000 flight history", "Airport status for flight ZX-5000"),
        SearchCandidate("https://flight-three.example/zx-5000", "AirlineCo ZX-5000 airline status", "Flight ZX-5000 arrival information"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"


def test_multiword_brand_is_preserved_when_cross_source_evidence_agrees():
    identity = ProductIdentity(mpn="ZX-5100")
    candidates = [
        SearchCandidate("https://northstar.example/zx-5100", "North Star ZX-5100 Sensor", "North Star ZX-5100 product"),
        SearchCandidate("https://dealer.example/north-star-zx-5100", "North Star ZX-5100 specifications", "Manufacturer: North Star"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "North Star"


def test_bootstrap_candidate_filter_requires_full_raw_identity_not_partial_noise():
    raw = "V15 G4 IRU"
    candidates = [
        SearchCandidate("https://lenovo.example/v15-g4-iru", "Lenovo V15 G4 IRU", "Laptop specifications"),
        SearchCandidate("https://phones.example/vivo-v15", "vivo V15", "Phone specifications"),
        SearchCandidate("https://vacuum.example/v15", "Dyson V15 Detect", "Vacuum cleaner"),
    ]
    filtered = filter_bootstrap_candidates(raw, candidates)
    assert [c.url for c in filtered] == ["https://lenovo.example/v15-g4-iru"]


def test_generation_alias_gen_4_matches_g4_without_accepting_partial_v15():
    raw = "V15 G4 IRU"
    candidates = [
        SearchCandidate("https://lenovo.example/v15-gen-4-iru", "Lenovo V15 Gen 4 IRU", "Business laptop"),
        SearchCandidate("https://noise.example/v15", "V15 laptop", "Generic result"),
    ]
    filtered = filter_bootstrap_candidates(raw, candidates)
    assert [c.url for c in filtered] == ["https://lenovo.example/v15-gen-4-iru"]


def test_context_terms_learn_repeated_product_context_without_assigning_brand():
    raw = "A2794"
    candidates = [
        SearchCandidate("https://one.example/a2794", "Apple 240W USB-C Charge Cable A2794", "Apple USB-C cable"),
        SearchCandidate("https://two.example/a2794", "A2794 Apple USB C cable 240W", "Charge cable for Mac"),
        SearchCandidate("https://three.example/a2794", "AAL2794 flight tracking", "American Airlines flight A2794"),
    ]
    terms = derive_context_terms(raw, candidates)
    queries = build_context_queries(raw, terms)
    assert "apple" in {term.lower() for term in terms[:3]}
    assert any('"A2794" "Apple"' in q or '"A2794" "apple"' in q for q in queries)
    assert all("flight" not in q.lower() for q in queries[:2])


def test_context_terms_never_return_the_raw_identifier_itself():
    raw = "ZX5000A"
    candidates = [
        SearchCandidate("https://one.example/zx5000a", "Acme ZX5000A sensor", "ZX5000A technical product"),
        SearchCandidate("https://two.example/zx5000a", "ZX5000A Acme specifications", "Acme ZX5000A"),
        SearchCandidate("https://three.example/zx5000a", "ZX5000A product details", "ZX5000A sensor"),
    ]
    terms = derive_context_terms(raw, candidates)
    assert raw.lower() not in {term.lower() for term in terms}


def test_discovery_fallback_queries_are_broad_but_do_not_invent_brand():
    queries = build_discovery_fallback_queries("MF455dw")
    assert "MF455dw" in queries
    assert "MF455dw product" in queries
    assert all('"' not in q for q in queries)
    assert all("Canon" not in q for q in queries)


def test_page_backed_brand_can_resolve_when_serp_title_does_not_expose_brand():
    identity = ProductIdentity(product_name="Rugged 77")
    candidates = [
        SearchCandidate("https://maker.example/products/rugged-77", "Rugged 77 specifications", "Technical product information"),
        SearchCandidate("https://dealer.example/rugged-77", "Rugged 77 phone", "Product details"),
    ]
    page_signals = [
        PageIdentitySignal(url="https://maker.example/products/rugged-77", brand="ExampleTech", model="Rugged 77", product_name="ExampleTech Rugged 77", exact_raw_match=True, material=True, structured_brand=True, authority_owned=True),
        PageIdentitySignal(url="https://dealer.example/rugged-77", brand="ExampleTech", model="Rugged 77", product_name="ExampleTech Rugged 77", exact_raw_match=True, material=True),
    ]
    result = resolve_identity_with_page_signals(identity, candidates, page_signals)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "ExampleTech"
    assert result.identity.model == "Rugged 77"
    assert result.brand_hosts["ExampleTech"] == 2
    assert result.official_domain_hint == "maker.example"


def test_page_backed_conflicting_brand_remains_unresolved_even_with_exact_raw_match():
    identity = ProductIdentity(mpn="ZX-4109")
    candidates = [
        SearchCandidate("https://one.example/zx-4109", "ZX-4109", "Product"),
        SearchCandidate("https://two.example/zx-4109", "ZX-4109", "Product"),
    ]
    page_signals = [
        PageIdentitySignal(url="https://one.example/zx-4109", brand="Acme", model="ZX-4109", exact_raw_match=True, material=True, structured_brand=True),
        PageIdentitySignal(url="https://two.example/zx-4109", brand="Nova", model="ZX-4109", exact_raw_match=True, material=True, structured_brand=True),
    ]
    result = resolve_identity_with_page_signals(identity, candidates, page_signals)
    assert result.status == "IDENTITY_UNRESOLVED"
    assert result.identity.brand is None
    assert result.reason == "AMBIGUOUS_BRAND"


def test_page_signal_without_exact_product_binding_cannot_resolve_brand():
    identity = ProductIdentity(product_name="Rugged 77")
    candidates = [SearchCandidate("https://maker.example/category", "Phones", "ExampleTech products")]
    page_signals = [PageIdentitySignal(url="https://maker.example/category", brand="ExampleTech", product_name="Other Model", exact_raw_match=False, material=True, structured_brand=True, authority_owned=True)]
    result = resolve_identity_with_page_signals(identity, candidates, page_signals)
    assert result.status == "IDENTITY_UNRESOLVED"
    assert result.identity.brand is None
    assert result.official_domain_hint is None


def test_identity_page_probe_budget_is_bounded_for_fast_bootstrap():
    max_probes, timeout_seconds = identity_probe_budget()
    assert max_probes <= 4
    assert timeout_seconds <= 8


def test_bootstrap_queries_do_not_invent_brand_before_resolution():
    identity = ProductIdentity(product_name="Armor 22")
    queries = build_bootstrap_queries(identity)
    assert queries[0] == '"Armor 22"'
    assert all("Ulefone" not in q for q in queries)
    assert any("specifications" in q for q in queries)
    assert any("manufacturer" in q.lower() for q in queries)


def test_deep_queries_use_brand_only_after_it_is_resolved():
    identity = ProductIdentity(brand="Acme", mpn="ZX-4109")
    queries = build_deep_queries(identity, official_domain_hint="acme.example")
    assert any('"ZX-4109" "Acme"' in q for q in queries)
    assert any('site:acme.example "ZX-4109"' in q for q in queries)
    assert any("pdf" in q.lower() for q in queries)
