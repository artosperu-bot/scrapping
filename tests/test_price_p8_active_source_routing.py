import json

from product_intelligence import price_workflow
from product_intelligence.models import ProductIdentity
from product_intelligence.price_models import PriceOffer
from product_intelligence.price_source_capabilities import SourceCapabilityRegistry


def _ssd_identity():
    return ProductIdentity(
        brand="ExampleBrand",
        product_name="ExampleBrand SSD 960GB",
        model="Model 123 SSD",
        mpn="ABC/123",
    )


def _audio_identity():
    return ProductIdentity(
        brand="ExampleBrand",
        product_name="ExampleBrand wireless headphones",
        model="Audio 123",
        mpn="AUD/123",
    )


def _offer(url="https://learned-shop.pe/product/abc123", price=499.0, channel="Learned Shop"):
    return PriceOffer(
        part_number="ABC/123",
        brand="ExampleBrand",
        model="Model 123 SSD",
        channel=channel,
        seller_display_name=channel,
        selling_price=price,
        currency="PEN",
        url=url,
        confidence=1.0,
        identity_match="EXACT_MPN",
        source_type="api",
        source_method="vtex_catalog",
    )


def _seed_vtex(registry, domain="learned-shop.pe", *, category="PC_COMPONENT"):
    registry.record(
        f"https://{domain}/product/seed",
        platform="vtex",
        discovery_method="open_web",
        extraction_method="vtex_catalog",
        price_capable=True,
        stock_capable=True,
        seller_capable=True,
        success=True,
        category=category,
    )


def _silence_persistence(monkeypatch):
    monkeypatch.setattr(price_workflow, "save_price_run", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_channel_coverage", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_validated_source_bindings", lambda *_a, **_k: None)


def _silence_other_lanes(monkeypatch, *, provider_urls=()):
    monkeypatch.setattr(price_workflow, "PERU_STRUCTURED_SOURCES", ())
    monkeypatch.setattr(price_workflow, "_try_mercadolibre", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "load_validated_source_urls", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_additional_peru_pdps", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_general_peru_retailers", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_price_sources", lambda *_a, **_k: list(provider_urls))


def test_learned_vtex_capability_is_selected_for_direct_routing(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_vtex(registry)

    rows = registry.direct_candidates(_ssd_identity())

    assert [row["domain"] for row in rows] == ["learned-shop.pe"]
    assert rows[0]["direct_method"] == "vtex_catalog"
    assert rows[0]["source_recovery_method"] == "DIRECT_SOURCE"


def test_category_incompatible_learned_source_is_not_selected(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_vtex(registry, category="AUDIO")

    assert registry.direct_candidates(_ssd_identity()) == []
    assert registry.direct_candidates(_audio_identity())


def test_cold_start_does_not_magically_know_unlearned_source(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)

    assert registry.direct_candidates(_ssd_identity()) == []
    assert registry.get("never-seen.example") is None


def test_one_failure_does_not_permanently_blacklist_learned_capability(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_vtex(registry)
    registry.record(
        "learned-shop.pe",
        platform="vtex",
        discovery_method="direct_vtex_catalog",
        success=False,
        category="PC_COMPONENT",
    )

    learned = registry.get("learned-shop.pe")
    assert learned["last_failure"]
    assert 0.0 < learned["health"] < 1.0
    assert registry.direct_candidates(_ssd_identity())[0]["domain"] == "learned-shop.pe"


def test_warm_capability_routes_directly_even_when_provider_returns_zero(tmp_path, monkeypatch):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_vtex(registry)
    calls = {"direct": 0, "provider": 0}
    fresh = _offer()

    _silence_persistence(monkeypatch)
    _silence_other_lanes(monkeypatch)

    def direct(url, identity, channel, timeout=12):
        calls["direct"] += 1
        assert "learned-shop.pe" in url
        return [fresh]

    def provider(*_a, **_k):
        calls["provider"] += 1
        return []

    monkeypatch.setattr(price_workflow, "_try_vtex", direct)
    monkeypatch.setattr(price_workflow, "discover_price_sources", provider)

    rows = price_workflow.run_price_product(_ssd_identity(), tmp_path)

    assert calls["direct"] == 1
    assert calls["provider"] == 1
    assert [(row.channel, row.selling_price) for row in rows] == [("Learned Shop", 499.0)]


def test_stale_direct_capability_falls_back_to_provider(tmp_path, monkeypatch):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_vtex(registry, domain="stale-shop.pe")
    fallback_url = "https://fresh-shop.pe/product/abc123"
    fallback = _offer(fallback_url, 519.0, "Fresh Shop")
    calls = {"direct": 0, "provider": 0}

    _silence_persistence(monkeypatch)
    _silence_other_lanes(monkeypatch, provider_urls=(fallback_url,))

    def direct(*_a, **_k):
        calls["direct"] += 1
        raise RuntimeError("temporary endpoint failure")

    def provider(*_a, **_k):
        calls["provider"] += 1
        return [fallback_url]

    original_collect = price_workflow._collect_web_offers

    def collect(sources, *_a, **_k):
        if fallback_url in sources:
            return [fallback]
        return original_collect(sources, *_a, **_k)

    monkeypatch.setattr(price_workflow, "_try_vtex", direct)
    monkeypatch.setattr(price_workflow, "discover_price_sources", provider)
    monkeypatch.setattr(price_workflow, "_collect_web_offers", collect)

    rows = price_workflow.run_price_product(_ssd_identity(), tmp_path)

    assert calls == {"direct": 1, "provider": 1}
    assert [(row.channel, row.selling_price) for row in rows] == [("Fresh Shop", 519.0)]


def test_direct_source_never_reuses_cached_old_price_as_fresh(tmp_path, monkeypatch):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_vtex(registry)
    path = tmp_path / "price_intelligence" / "source_capabilities.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["learned-shop.pe"]["cached_price"] = 1.0
    path.write_text(json.dumps(data), encoding="utf-8")
    fresh = _offer(price=499.0)

    _silence_persistence(monkeypatch)
    _silence_other_lanes(monkeypatch)
    monkeypatch.setattr(price_workflow, "_try_vtex", lambda *_a, **_k: [fresh])

    rows = price_workflow.run_price_product(_ssd_identity(), tmp_path)

    assert [row.selling_price for row in rows] == [499.0]
    assert all(row.selling_price != 1.0 for row in rows)


def test_direct_vtex_result_still_passes_existing_identity_gate(tmp_path, monkeypatch):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_vtex(registry)

    class Response:
        status_code = 200
        def json(self):
            return [{
                "productId": "WRONG",
                "productName": "ExampleBrand SSD 960GB",
                "brand": "ExampleBrand",
                "description": "NUMERO DE PARTE WRONG-999",
                "items": [{
                    "itemId": "SKU-WRONG",
                    "name": "SSD 960GB",
                    "sellers": [{
                        "sellerId": "seller-x",
                        "sellerName": "Seller X",
                        "commertialOffer": {"Price": 199, "AvailableQuantity": 3, "IsAvailable": True},
                    }],
                }],
            }]

    monkeypatch.setattr(price_workflow.requests, "get", lambda *_a, **_k: Response())
    capabilities = registry.direct_candidates(_ssd_identity())

    rows = price_workflow._collect_direct_source_offers(
        capabilities,
        _ssd_identity(),
        lambda *_a, **_k: None,
        capability_registry=registry,
    )

    assert rows == []


def test_one_direct_source_failure_does_not_block_other_source_worker(tmp_path, monkeypatch):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_vtex(registry, domain="broken-shop.pe")
    _seed_vtex(registry, domain="healthy-shop.pe")
    fresh = _offer("https://healthy-shop.pe/product/abc123", 509.0, "Healthy Shop")

    def direct(url, *_a, **_k):
        if "broken-shop.pe" in url:
            raise RuntimeError("broken source")
        return [fresh]

    monkeypatch.setattr(price_workflow, "_try_vtex", direct)
    capabilities = registry.direct_candidates(_ssd_identity())

    rows = price_workflow._collect_direct_source_offers(
        capabilities,
        _ssd_identity(),
        lambda *_a, **_k: None,
        capability_registry=registry,
    )

    assert [(row.channel, row.selling_price) for row in rows] == [("Healthy Shop", 509.0)]
