from product_intelligence.models import ProductIdentity


def test_refinement_normalizes_raw_provider_tuples_before_candidate_logic(monkeypatch):
    from product_intelligence import identity_refinement as refinement

    original = ProductIdentity(mpn="ABC123", model="ABC123")
    current = ProductIdentity(mpn="ABC123", model="ABC123")
    raw_rows = [
        ("https://acme.com/ABC123.html", "Acme Model X ABC123", "Official product"),
        ("https://retailer-one.example/acme-model-x-abc123", "Acme Model X ABC123", "Retail listing"),
        ("https://retailer-two.example/acme-model-x-abc123", "Acme Model X ABC123", "Retail listing"),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_args, **_kwargs: raw_rows)

    result = refinement.refine_code_identity(original, current, timeout=1, max_queries=1)

    assert result.candidates_used == 3
    assert result.identity.brand is not None
    assert result.identity.model is not None
    assert result.identity.model != "ABC123"
    assert result.official_domain_hint == "acme.com"


def test_refinement_keeps_accepting_search_candidate_objects(monkeypatch):
    from product_intelligence import identity_refinement as refinement
    from product_intelligence.discovery import SearchCandidate

    original = ProductIdentity(mpn="ABC123", model="ABC123")
    current = ProductIdentity(mpn="ABC123", model="ABC123")
    candidates = [
        SearchCandidate("https://acme.com/ABC123.html", "Acme Model X ABC123", "Official product", 1.0, True),
        SearchCandidate("https://retailer-one.example/acme-model-x-abc123", "Acme Model X ABC123", "Retail listing", 0.9, False),
        SearchCandidate("https://retailer-two.example/acme-model-x-abc123", "Acme Model X ABC123", "Retail listing", 0.9, False),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_args, **_kwargs: candidates)

    result = refinement.refine_code_identity(original, current, timeout=1, max_queries=1)

    assert result.candidates_used == 3
    assert result.official_domain_hint == "acme.com"
