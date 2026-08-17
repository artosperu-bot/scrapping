from product_intelligence import identity_refinement as refinement
from product_intelligence.models import ProductIdentity


def test_refinement_normalizes_raw_provider_tuples(monkeypatch):
    original = ProductIdentity(mpn="ABC123", model="ABC123")
    rows = [
        ("https://acme.com/ABC123.html", "Acme Model X1 ABC123", "Official product"),
        ("https://retailer-one.example/acme-model-x1", "Acme Model X1", "MPN ABC123"),
        ("https://retailer-two.example/acme-model-x1", "Acme Model X1", "Part number ABC123"),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_a, **_k: rows)
    result = refinement.refine_code_identity(original, original, timeout=1, max_queries=1)
    assert result.candidates_used == 3
    assert (result.identity.brand or "").lower() == "acme"
    assert "model x1" in (result.identity.model or "").lower()
    assert result.official_domain_hint == "acme.com"


def test_snippet_bound_identifier_requires_descriptive_title_and_can_join_consensus(monkeypatch):
    raw = "ABC123XYZ"
    rows = [
        ("https://retailer-one.example/p/model", "Acme Tune 530C Wired Headphones", f"MPN {raw}"),
        ("https://retailer-two.example/product/530c", "Acme Tune 530C USB-C Headphones", f"Part number {raw}"),
        ("https://support.acme.com/tune-530c", "Acme Tune 530C Support", f"Model code {raw}"),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_a, **_k: rows)
    original = ProductIdentity(mpn=raw, model=raw)
    result = refinement.refine_code_identity(original, original, timeout=1, max_queries=1)
    assert result.candidates_used == 3
    assert (result.identity.brand or "").lower() == "acme"
    assert "tune" in (result.identity.model or "").lower()
    assert "530" in (result.identity.model or "").lower()


def test_single_retailer_hostname_cannot_become_product_brand(monkeypatch):
    raw = "ABC123"
    rows = [
        ("https://phonix-usa.example/p/abc123", "Phonix USA Acme Model X1", raw),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_a, **_k: rows)
    original = ProductIdentity(mpn=raw, model=raw)
    result = refinement.refine_code_identity(original, original, timeout=1, max_queries=1)
    assert (result.identity.brand or "").lower() != "phonix usa"
    assert not (result.official_domain_hint or "").startswith("phonix-usa")


def test_url_tokens_never_become_brand(monkeypatch):
    raw = "ABC123"
    rows = [
        ("https://store-one.example/p/abc123", "www Acme Model X1 ABC123", raw),
        ("https://store-two.example/p/abc123", "www Acme Model X1 ABC123", raw),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_a, **_k: rows)
    original = ProductIdentity(mpn=raw, model=raw)
    result = refinement.refine_code_identity(original, original, timeout=1, max_queries=1)
    assert (result.identity.brand or "").lower() not in {"www", "http", "https", "com", "net", "org"}


def test_stable_model_core_strips_marketing_tail():
    assert hasattr(refinement, "stable_model_core")
    value = "Acme Tune 530C Hi-res USB-C Wired On-ear Headphones In Black - ABC123"
    assert refinement.stable_model_core(value, raw="ABC123", brand="Acme").lower() == "tune 530c"


def test_url_protocol_tokens_cannot_become_product_model(monkeypatch):
    raw = "ZX530CBLKAM"
    rows = [
        ("https://store-one.example/p/zx530cblkam", "Nova https www ZX530CBLKAM", raw),
        ("https://store-two.example/p/zx530cblkam", "Nova https www ZX530CBLKAM", raw),
        ("https://catalog-three.example/p/zx530cblkam", "Nova https www ZX530CBLKAM", raw),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_a, **_k: rows)
    original = ProductIdentity(mpn=raw, model=raw)

    result = refinement.refine_code_identity(original, original, timeout=1, max_queries=1)

    model = (result.identity.model or "").strip().lower()
    assert model not in {"https www", "www https", "http www", "www http"}
    assert not ({"http", "https", "www", "com", "net", "org"} >= set(model.split()) and model != raw.lower())


def test_mpn_fragment_brand_hint_is_not_preserved_over_cross_domain_brand_consensus(monkeypatch):
    raw = "ZX530CBLKAM"
    poisoned = ProductIdentity(brand="530CBLKAM Tune", mpn=raw, model=raw)
    rows = [
        ("https://retailer-one.example/p/zx530cblkam", "Nova Tune 530C Wired Headphones", f"MPN {raw}"),
        ("https://retailer-two.example/p/zx530cblkam", "Nova Tune 530C USB-C Headphones", f"Part number {raw}"),
        ("https://support.nova.example/tune-530c", "Nova Tune 530C Support", f"Model code {raw}"),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_a, **_k: rows)
    original = ProductIdentity(mpn=raw, model=raw)

    result = refinement.refine_code_identity(original, poisoned, timeout=1, max_queries=1)

    assert (result.identity.brand or "").lower() == "nova"
    assert "530cblkam" not in (result.identity.brand or "").lower()


def test_identity_sanity_pass_rejects_url_model_and_code_fragment_brand():
    assert hasattr(refinement, "identity_sanity_pass")
    raw = "ZX530CBLKAM"
    assert not refinement.identity_sanity_pass(
        ProductIdentity(brand="530CBLKAM Tune", model="https www", mpn=raw),
        raw=raw,
    )
    assert refinement.identity_sanity_pass(
        ProductIdentity(brand="Nova", model="Tune 530C", mpn=raw),
        raw=raw,
    )
