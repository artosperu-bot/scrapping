from product_intelligence import identity_refinement as refinement
from product_intelligence.models import ProductIdentity


def test_single_retailer_hostname_cannot_override_cross_domain_product_brand(monkeypatch):
    raw = "PART123"
    rows = [
        ("https://retailer-one.example/p/part123", "Acme Model X Wireless Headphones", raw),
        ("https://retailer-two.example/item/model-x", "Acme Model X Headphones", f"MPN {raw}"),
        ("https://loyaltysource.example/acme-model-x", "LoyaltySource Acme Model X", f"Part number {raw}"),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda query, timeout: rows)
    original = ProductIdentity(model=raw, mpn=raw)
    result = refinement.refine_code_identity(original, original)
    assert result.identity.brand.lower() == "acme"
    assert result.official_domain_hint is None or "loyaltysource" not in result.official_domain_hint


def test_brand_can_be_recovered_from_descriptive_bootstrap_model(monkeypatch):
    raw = "PART123"
    rows = [
        ("https://store-a.example/item", "Acme Model X Waterproof Wireless Headphones", f"MPN {raw}"),
        ("https://store-b.example/item", "Acme Model X Wireless Headphones", f"MPN {raw}"),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda query, timeout: rows)
    original = ProductIdentity(model=raw, mpn=raw)
    current = ProductIdentity(model="Acme Model X Waterproof Wireless Headphones", mpn=raw)
    result = refinement.refine_code_identity(original, current)
    assert result.identity.brand.lower() == "acme"
    assert "model" in result.identity.model.lower()
