from types import SimpleNamespace

from product_intelligence.models import ProductIdentity
from product_intelligence.price_identity_resolution import resolve_price_identity
from product_intelligence.price_queries import build_price_query_plan


def test_price_identity_resolution_accepts_evidence_backed_bootstrap():
    original = ProductIdentity(mpn="ABC/123")
    learned = ProductIdentity(mpn="ABC/123", brand="ExampleBrand", model="Example Model 123")

    def bootstrap(_identity, **_kwargs):
        return SimpleNamespace(
            status="RESOLVED",
            identity=learned,
            confidence=.94,
            reason="PAGE_BACKED_IDENTITY_RESOLUTION",
            official_domain_hint="examplebrand.com",
            page_probes_succeeded=1,
            brand_hosts={"ExampleBrand": 2},
            candidate_urls=["https://examplebrand.com/product/abc123"],
            page_signals=[],
        )

    result = resolve_price_identity(original, bootstrap=bootstrap)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "ExampleBrand"
    assert result.identity.model == "Example Model 123"
    assert result.input_identity.mpn == "ABC/123"
    assert result.evidence_backed is True


def test_price_identity_resolution_falls_back_when_resolver_fails():
    original = ProductIdentity(mpn="ABC/123")

    def broken(_identity, **_kwargs):
        raise RuntimeError("network unavailable")

    result = resolve_price_identity(original, bootstrap=broken)
    assert result.status == "FALLBACK_ORIGINAL"
    assert result.identity.model_dump() == original.model_dump()
    assert result.error == "RuntimeError"


def test_price_identity_resolution_rejects_generic_brand_even_if_marked_resolved():
    original = ProductIdentity(mpn="ABC/123")
    bad = ProductIdentity(mpn="ABC/123", brand="DISCO DURO", model="SSD 960GB")

    def bootstrap(_identity, **_kwargs):
        return SimpleNamespace(
            status="RESOLVED", identity=bad, confidence=.99, reason="CROSS_SOURCE_BRAND_RESOLUTION",
            official_domain_hint=None, page_probes_succeeded=0, brand_hosts={"DISCO DURO": 3},
            candidate_urls=[], page_signals=[],
        )

    result = resolve_price_identity(original, bootstrap=bootstrap)
    assert result.status == "REJECTED_RESOLUTION"
    assert result.identity.brand is None
    assert result.identity.mpn == "ABC/123"


def test_price_query_plan_is_bounded_ordered_and_signal_aware():
    identity = ProductIdentity(
        brand="ExampleBrand",
        model="Model 123",
        mpn="ABC/123",
        upc="036000291452",
    )
    rows = build_price_query_plan(identity)
    queries = [row.query for row in rows]

    assert queries[0] == "ABC/123"
    assert "ABC123" in queries
    assert "ABC-123" in queries
    assert "ABC 123" in queries
    assert 'ExampleBrand ABC/123' in queries
    assert "036000291452" in queries
    assert "ExampleBrand Model 123" in queries
    assert len(queries) == len(set(q.casefold() for q in queries))
    assert len(queries) <= 12
    assert all(row.signal_type for row in rows)


def test_query_plan_does_not_use_invalid_gtin_signal():
    identity = ProductIdentity(mpn="ABC/123", gtin="NOT-A-GTIN")
    queries = [row.query for row in build_price_query_plan(identity)]
    assert "NOT-A-GTIN" not in queries
