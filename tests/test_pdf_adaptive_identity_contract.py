from product_intelligence import identity_refinement as refinement
from product_intelligence.models import ProductIdentity


def test_refinement_normalizes_raw_provider_tuples(monkeypatch):
    original = ProductIdentity(mpn="ABC123", model="ABC123")
    rows = [
        ("https://acme.com/ABC123.html", "Acme Model X ABC123", "Official product"),
        ("https://retailer-one.example/acme-model-x", "Acme Model X", "MPN ABC123"),
        ("https://retailer-two.example/acme-model-x", "Acme Model X", "Part number ABC123"),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_a, **_k: rows)
    result = refinement.refine_code_identity(original, original, timeout=1, max_queries=1)
    assert result.candidates_used == 3
    assert (result.identity.brand or "").lower() == "acme"
    assert "model x" in (result.identity.model or "").lower()
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
        ("https://phonix-usa.example/p/abc123", "Phonix USA Acme Model X", raw),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_a, **_k: rows)
    original = ProductIdentity(mpn=raw, model=raw)
    result = refinement.refine_code_identity(original, original, timeout=1, max_queries=1)
    assert (result.identity.brand or "").lower() != "phonix usa"
    assert not (result.official_domain_hint or "").startswith("phonix-usa")


def test_url_tokens_never_become_brand(monkeypatch):
    raw = "ABC123"
    rows = [
        ("https://store-one.example/p/abc123", "www Acme Model X ABC123", raw),
        ("https://store-two.example/p/abc123", "www Acme Model X ABC123", raw),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_a, **_k: rows)
    original = ProductIdentity(mpn=raw, model=raw)
    result = refinement.refine_code_identity(original, original, timeout=1, max_queries=1)
    assert (result.identity.brand or "").lower() not in {"www", "http", "https", "com", "net", "org"}


def test_stable_model_core_strips_marketing_tail():
    assert hasattr(refinement, "stable_model_core")
    value = "Acme Tune 530C Hi-res USB-C Wired On-ear Headphones In Black - ABC123"
    assert refinement.stable_model_core(value, raw="ABC123", brand="Acme").lower() == "tune 530c"
