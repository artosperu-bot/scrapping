from product_intelligence.models import ProductIdentity


def test_refinement_can_replace_noisy_bootstrap_brand_with_cross_domain_consensus(monkeypatch):
    from product_intelligence import identity_refinement as refinement

    original = ProductIdentity(mpn="ABC123", model="ABC123")
    current = ProductIdentity(
        brand="blue HEADPHONE",
        model="HEADPHONE ACME MODEL X ABC123 BLUE",
        mpn="ABC123",
    )
    rows = [
        ("https://acme.com/ABC123", "Acme Model X ABC123", "Official product"),
        ("https://retailer-one.example/acme-model-x-abc123", "Acme Model X ABC123", "Retail listing"),
        ("https://retailer-two.example/acme-model-x-abc123", "Acme Model X ABC123", "Retail listing"),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_args, **_kwargs: rows)

    result = refinement.refine_code_identity(original, current, timeout=1, max_queries=1)

    assert result.identity.brand.lower() == "acme"
    assert "model x" in (result.identity.model or "").lower()
    assert result.official_domain_hint == "acme.com"
