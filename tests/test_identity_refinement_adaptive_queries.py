from product_intelligence.models import ProductIdentity


def test_sparse_exact_identity_search_escalates_to_support_queries(monkeypatch):
    from product_intelligence import identity_refinement as refinement

    original = ProductIdentity(mpn="ABC123", model="ABC123")
    current = ProductIdentity(mpn="ABC123", model="ABC123")
    calls: list[str] = []

    corroborated = [
        ("https://acme.com/products/abc123", "Acme Model X", "ABC123 support downloads"),
        ("https://retailer-one.example/acme-model-x", "Acme Model X", "ABC123 specifications"),
        ("https://retailer-two.example/acme-model-x", "Acme Model X", "ABC123 support"),
    ]

    def fake_search(query, _timeout):
        calls.append(query)
        if "support downloads" in query:
            return corroborated
        return []

    monkeypatch.setattr(refinement, "_provider_search", fake_search)

    result = refinement.refine_code_identity(original, current, timeout=1, max_queries=5)

    assert any("support downloads" in query for query in calls)
    assert result.identity.brand == "acme"
    assert result.identity.model.lower() == "model x"
    assert result.official_domain_hint == "acme.com"
    assert result.brand_support_domains >= 2
    assert result.model_support_domains >= 2
