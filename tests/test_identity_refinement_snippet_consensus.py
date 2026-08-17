from product_intelligence import identity_refinement as refinement
from product_intelligence.models import ProductIdentity


def test_refinement_uses_descriptive_titles_when_raw_code_is_bound_in_snippet(monkeypatch):
    raw = "ABC123XYZ"
    rows = [
        ("https://retailer-one.example/p/model", "Acme Tune 530C Wired Headphones", f"MPN {raw} official item"),
        ("https://retailer-two.example/product/530c", "Acme Tune 530C USB-C Headphones", f"Part number: {raw}"),
        ("https://support.acme.example/tune-530c", "Acme Tune 530C Support", f"Model code {raw}"),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda query, timeout: rows)
    original = ProductIdentity(model=raw, mpn=raw)
    current = ProductIdentity(model=raw, mpn=raw)
    result = refinement.refine_code_identity(original, current)
    assert result.candidates_used == 3
    assert result.identity.brand.lower() == "acme"
    assert "tune" in result.identity.model.lower()
    assert "530" in result.identity.model.lower()


def test_refinement_does_not_use_generic_query_echo_snippet_as_identity(monkeypatch):
    raw = "ABC123XYZ"
    rows = [
        ("https://example-one.test/search", "Search results", f"Results for {raw}"),
        ("https://example-two.test/category", "Products online", f"Search {raw}"),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda query, timeout: rows)
    original = ProductIdentity(model=raw, mpn=raw)
    result = refinement.refine_code_identity(original, original)
    assert result.candidates_used == 0
