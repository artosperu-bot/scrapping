from product_intelligence import price_workflow
from product_intelligence.models import ProductIdentity
from product_intelligence.price_models import PriceOffer
from product_intelligence.price_peru_coverage import _general_retail_query_specs
from product_intelligence.price_source_capabilities import SourceCapabilityRegistry


def _identity(category_name="ExampleBrand SSD 960GB", mpn="ABC/123"):
    return ProductIdentity(brand="ExampleBrand", product_name=category_name, model=category_name, mpn=mpn)


def _seed(registry, domain, *, platform="custom", category="PC_COMPONENT", success=True, price_capable=True):
    registry.record(
        domain,
        platform=platform,
        discovery_method="open_web",
        extraction_method="jsonld",
        price_capable=price_capable,
        success=success,
        category=category,
    )


def _offer(domain="direct-shop.pe"):
    return PriceOffer(
        part_number="ABC/123",
        brand="ExampleBrand",
        model="ExampleBrand SSD 960GB",
        channel="Direct Shop",
        seller_display_name="Direct Shop",
        selling_price=499.0,
        currency="PEN",
        url=f"https://{domain}/product/abc123",
        confidence=1.0,
        identity_match="EXACT_MPN",
        source_type="api",
        source_method="vtex_catalog",
    )


def test_provider_fallback_domains_are_bounded_and_category_aware(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    for index in range(10):
        _seed(registry, f"learned-{index}.pe")
    _seed(registry, "audio-only.pe", category="AUDIO")

    rows = registry.provider_fallback_domains(_identity(), limit=4)

    assert len(rows) == 4
    assert "audio-only.pe" not in rows
    assert all(domain.startswith("learned-") for domain in rows)


def test_successful_direct_and_structured_domains_can_be_excluded_from_provider_fallback(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed(registry, "direct-shop.pe", platform="vtex")
    _seed(registry, "structured-shop.pe", platform="vtex")
    _seed(registry, "fallback-shop.pe")

    rows = registry.provider_fallback_domains(
        _identity(),
        limit=4,
        exclude_domains=("direct-shop.pe", "structured-shop.pe"),
    )

    assert rows == ["fallback-shop.pe"]


def test_one_failure_does_not_make_learned_source_ineligible_for_provider_fallback(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed(registry, "temporarily-failed.pe")
    registry.record(
        "temporarily-failed.pe",
        platform="custom",
        discovery_method="direct_source",
        success=False,
        category="PC_COMPONENT",
    )

    assert "temporarily-failed.pe" in registry.provider_fallback_domains(_identity(), limit=4)


def test_four_provider_fallback_domains_add_at_most_twelve_learned_domain_queries():
    specs = _general_retail_query_specs(
        _identity(),
        priority_domains=("one.pe", "two.pe", "three.pe", "four.pe"),
    )
    learned = [(query, signal) for query, signal in specs if signal.startswith("LEARNED_DOMAIN")]

    assert len(learned) <= 12
    assert {query.split("site:", 1)[1] for query, _signal in learned} == {"one.pe", "two.pe", "three.pe", "four.pe"}


def test_workflow_computes_provider_fallback_after_direct_success(tmp_path, monkeypatch):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed(registry, "direct-shop.pe", platform="vtex")
    for domain in ("fallback-a.pe", "fallback-b.pe", "fallback-c.pe", "fallback-d.pe", "fallback-e.pe"):
        _seed(registry, domain)

    captured = []
    original_init = price_workflow.SourceCapabilityRegistry

    monkeypatch.setattr(price_workflow, "SourceCapabilityRegistry", lambda _root: registry)
    monkeypatch.setattr(price_workflow, "PERU_STRUCTURED_SOURCES", ())
    monkeypatch.setattr(price_workflow, "_try_mercadolibre", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "load_validated_source_urls", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "_collect_direct_source_offers", lambda *_a, **_k: [_offer()])
    monkeypatch.setattr(price_workflow, "discover_additional_peru_pdps", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_price_sources", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "_collect_web_offers", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "save_price_run", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_channel_coverage", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_validated_source_bindings", lambda *_a, **_k: None)

    def discover(_identity, *, limit, priority_domains, on_query_event=None):
        captured.append(tuple(priority_domains))
        return []

    monkeypatch.setattr(price_workflow, "discover_general_peru_retailers", discover)

    price_workflow.run_price_product(_identity(), tmp_path)

    assert captured
    priority = captured[0]
    assert "direct-shop.pe" not in priority
    assert len(priority) <= 4
    assert set(priority) <= {"fallback-a.pe", "fallback-b.pe", "fallback-c.pe", "fallback-d.pe", "fallback-e.pe"}
    monkeypatch.setattr(price_workflow, "SourceCapabilityRegistry", original_init)
