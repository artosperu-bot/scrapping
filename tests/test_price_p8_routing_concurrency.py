import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from product_intelligence import price_workflow
from product_intelligence.models import ProductIdentity
from product_intelligence.price_models import PriceOffer
from product_intelligence.price_source_capabilities import SourceCapabilityRegistry


def _identity():
    return ProductIdentity(
        brand="ExampleBrand",
        product_name="ExampleBrand SSD 960GB",
        model="Model 123 SSD",
        mpn="ABC/123",
    )


def _offer():
    return PriceOffer(
        part_number="ABC/123",
        brand="ExampleBrand",
        model="Model 123 SSD",
        channel="Healthy Shop",
        seller_display_name="Healthy Shop",
        selling_price=509.0,
        currency="PEN",
        url="https://healthy-shop.pe/product/abc123",
        confidence=1.0,
        identity_match="EXACT_MPN",
        source_type="api",
        source_method="vtex_catalog",
    )


def test_capability_persistence_failure_cannot_discard_fresh_offer(tmp_path, monkeypatch):
    registry = SourceCapabilityRegistry(tmp_path)
    registry.record(
        "https://healthy-shop.pe/product/seed",
        platform="vtex",
        discovery_method="open_web",
        extraction_method="vtex_catalog",
        price_capable=True,
        success=True,
        category="PC_COMPONENT",
    )
    capabilities = registry.direct_candidates(_identity())
    fresh = _offer()

    monkeypatch.setattr(price_workflow, "_try_vtex", lambda *_a, **_k: [fresh])
    monkeypatch.setattr(registry, "record", lambda *_a, **_k: (_ for _ in ()).throw(OSError("registry unavailable")))

    rows = price_workflow._collect_direct_source_offers(
        capabilities,
        _identity(),
        lambda *_a, **_k: None,
        capability_registry=registry,
    )

    assert [(row.channel, row.selling_price) for row in rows] == [("Healthy Shop", 509.0)]


def test_registry_serializes_concurrent_read_modify_write(tmp_path, monkeypatch):
    registry = SourceCapabilityRegistry(tmp_path)
    counter_lock = Lock()
    state = {"active": 0, "max_active": 0}

    def slow_save(_data):
        with counter_lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        time.sleep(0.04)
        with counter_lock:
            state["active"] -= 1

    monkeypatch.setattr(registry, "_save", slow_save)

    def write(index):
        registry.record(
            f"shop-{index}.pe",
            platform="vtex",
            discovery_method="direct_vtex_catalog",
            success=True,
            category="PC_COMPONENT",
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(8)))

    assert state["max_active"] == 1
