from product_intelligence.models import ProductIdentity
from product_intelligence.price_source_capabilities import SourceCapabilityRegistry
from product_intelligence.product_classification import classify_product


def _seed_hardware_source(registry):
    registry.record(
        "https://hardware-learned.pe/product/seed",
        platform="vtex",
        discovery_method="open_web",
        extraction_method="vtex_catalog",
        price_capable=True,
        success=True,
        category="PC_COMPONENT",
    )


def _identity(name, model, mpn):
    return ProductIdentity(brand="ExampleBrand", product_name=name, model=model, mpn=mpn)


def test_existing_category_router_keeps_matching_computing_source(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_hardware_source(registry)
    product = _identity("ExampleBrand SSD 1TB", "Fast SSD", "SSD-1000")

    assert classify_product(product).category == "PC_COMPONENT"
    assert [row["domain"] for row in registry.direct_candidates(product)] == ["hardware-learned.pe"]


def test_hardware_source_is_not_routed_for_audio(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_hardware_source(registry)
    product = _identity("Wireless Headphones", "Audio One", "AUD-1")

    assert classify_product(product).category == "AUDIO"
    assert registry.direct_candidates(product) == []


def test_hardware_source_is_not_routed_for_smartphone(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_hardware_source(registry)
    product = _identity("Rugged Smartphone", "Phone One", "PHN-1")

    assert classify_product(product).category == "SMARTPHONE"
    assert registry.direct_candidates(product) == []


def test_hardware_source_is_not_routed_for_power_tool(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_hardware_source(registry)
    product = _identity("Cordless Power Drill 20V", "Drill One", "TOOL-1")

    assert classify_product(product).category == "TOOL"
    assert registry.direct_candidates(product) == []


def test_hardware_source_is_not_routed_for_appliance(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_hardware_source(registry)
    product = _identity("Microwave Oven 25L", "Kitchen One", "APP-1")

    assert classify_product(product).category == "APPLIANCE"
    assert registry.direct_candidates(product) == []


def test_hardware_source_is_not_routed_for_non_electronic_baby_product(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    _seed_hardware_source(registry)
    product = _identity("Baby Diapers Size M", "Soft Care", "BABY-1")

    assert classify_product(product).category == "BABY_CARE"
    assert registry.direct_candidates(product) == []


def test_category_specific_learned_source_is_selected_for_matching_tool(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    registry.record(
        "https://tools-learned.pe/product/seed",
        platform="vtex",
        discovery_method="open_web",
        extraction_method="vtex_catalog",
        price_capable=True,
        success=True,
        category="TOOL",
    )
    product = _identity("Angle Grinder Power Tool", "Grinder One", "TOOL-2")

    rows = registry.direct_candidates(product)

    assert classify_product(product).category == "TOOL"
    assert [row["domain"] for row in rows] == ["tools-learned.pe"]
