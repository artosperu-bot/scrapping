from product_intelligence import price_workflow
from product_intelligence.models import ProductIdentity
from product_intelligence.price_models import PriceOffer
from product_intelligence.price_peru_coverage import _general_retail_queries
from product_intelligence.price_source_capabilities import SourceCapabilityRegistry


def _identity():
    return ProductIdentity(brand="ExampleBrand", model="Model 123", mpn="ABC/123")


def _offer(url="https://freshstore.pe/product/abc123"):
    return PriceOffer(
        part_number="ABC/123",
        brand="ExampleBrand",
        model="Model 123",
        channel="FreshStore",
        seller_display_name="FreshStore",
        selling_price=499.0,
        currency="PEN",
        url=url,
        confidence=1.0,
        identity_match="EXACT_MPN",
        source_type="structured",
        source_method="jsonld",
    )


def test_source_registry_exposes_only_successful_domains_for_future_priority(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    registry.record("https://failed.pe/product/x", platform="custom", success=False)
    registry.record("https://freshstore.pe/product/x", platform="jsonld", success=True)
    assert registry.successful_domains() == ["freshstore.pe"]


def test_open_peru_query_plan_can_prioritize_learned_domains_without_replacing_broad_discovery():
    queries = _general_retail_queries(_identity(), priority_domains=("freshstore.pe",))
    assert any("site:freshstore.pe" in query for query in queries)
    assert any("precio Perú" in query for query in queries)


def test_collect_web_offers_records_fresh_source_capability_observation(monkeypatch, tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    url = "https://freshstore.pe/product/abc123"
    html = '<html><script type="application/ld+json">{"@type":"Product"}</script></html>'
    row = _offer(url)

    monkeypatch.setattr(price_workflow, "_parse_page_with_dynamic_retry", lambda *_a, **_k: (html, [row]))
    monkeypatch.setattr(price_workflow, "_augment_page_rows", lambda *_a, **_k: [row])

    rows = price_workflow._collect_web_offers(
        [url], _identity(), lambda *_a, **_k: None,
        capability_registry=registry,
        discovery_method="open_web",
    )
    assert rows == [row]
    learned = registry.get("freshstore.pe")
    assert learned["platform"] == "jsonld"
    assert learned["success_count"] == 1
    assert learned["discovery_methods"] == ["open_web"]
    assert learned["extraction_methods"] == ["jsonld"]
    assert learned["last_success"]
