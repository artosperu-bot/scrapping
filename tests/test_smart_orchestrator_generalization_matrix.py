import pytest

from product_intelligence import discovery
from product_intelligence.field_resolution_planner import plan_field
from product_intelligence.models import ProductIdentity
from product_intelligence.product_classification import classify_product
from product_intelligence.source_router import route_sources


def _identity(brand, model, mpn):
    return ProductIdentity(
        brand=brand,
        model=model,
        mpn=mpn,
        confidence=.99,
        match_level="EXACT",
        identifiers_confirmed=["mpn"],
    )


MATRIX = [
    ("JBL", "Endurance Run 3 Wireless", "JBL-END-3-WL", "headphones", "driver_size", "AUDIO", "OFFICIAL_PDF"),
    ("Sony", "WH-1000XM6 Wireless", "WH1000XM6/B", "headphones", "frequency_response", "AUDIO", "OFFICIAL_PDF"),
    ("Apple", "iPhone 16 256GB Black", "MYE93LL/A", "smartphone", "battery_capacity", "SMARTPHONE", "MANUFACTURER"),
    ("Samsung", "Galaxy S25 256GB", "SM-S931BZKDEUB", "smartphone", "display_resolution", "SMARTPHONE", "MANUFACTURER"),
    ("Lenovo", "ThinkPad T14 Gen 5", "21ML000AUS", "laptop", "processor", "COMPUTER", "MANUFACTURER"),
    ("Dell", "Latitude 5450", "LAT5450-U7", "laptop pc", "display_resolution", "COMPUTER", "MANUFACTURER"),
    ("Brother", "MFC-L3780CDW", "MFCL3780CDW", "printer", "print_resolution", "PRINTER", "MANUFACTURER_SUPPORT"),
    ("Epson", "EcoTank ET-4850", "C11CJ60202", "printer", "print_resolution", "PRINTER", "MANUFACTURER_SUPPORT"),
    ("Kingston", "FURY Beast DDR5 32GB", "KF560C30BBE-32", "pc memory component", "voltage", "PC_COMPONENT", "MANUFACTURER"),
    ("Texas Instruments", "TPS5430", "TPS5430DDAR", "electronic component", "voltage", "ELECTRONIC_COMPONENT", "MANUFACTURER"),
    ("TP-Link", "Archer AX55", "ARCHER-AX55", "wifi router", "wifi_protocol", "NETWORK", "MANUFACTURER"),
    ("Logitech", "MX Master 3S", "910-006556", "wireless mouse accessory", "compatibility", "ACCESSORY", "MANUFACTURER_SUPPORT"),
    ("Stanley", "Quencher H2.0 30 oz", "10-10827-001", "insulated bottle", "package_contents", "GENERAL", "MANUFACTURER"),
]


@pytest.mark.parametrize("brand,model,mpn,description,field,expected_category,expected_first_kind", MATRIX)
def test_generalization_matrix_routes_by_category_and_field_not_brand(
    brand, model, mpn, description, field, expected_category, expected_first_kind
):
    identity = _identity(brand, model, mpn)
    classification = classify_product(identity, description=description, required_fields=[field])
    intents = route_sources(identity, (plan_field(field),), category=classification.category)

    assert classification.category == expected_category
    assert intents
    assert intents[0].source_kind == expected_first_kind
    assert intents[-1].engine in {"WEB_FALLBACK", "PDF", "WEB_STRUCTURED"}


def test_same_technical_field_changes_source_order_by_category_without_brand_rules():
    identity = _identity("ExampleCorp", "Model X", "EX-123")
    plan = plan_field("voltage")

    audio = route_sources(identity, (plan,), category="AUDIO")
    component = route_sources(identity, (plan,), category="ELECTRONIC_COMPONENT")
    printer = route_sources(identity, (plan,), category="PRINTER")

    assert audio[0].source_kind == "OFFICIAL_PDF"
    assert component[0].source_kind == "MANUFACTURER"
    assert any(intent.source_kind == "CATEGORY_PROVIDER" for intent in component)
    assert printer[0].source_kind == "MANUFACTURER_SUPPORT"


def test_source_intent_changes_real_field_search_query(monkeypatch):
    identity = _identity("ExampleCorp", "Print X1", "PX1")
    captured = []

    def fake_provider_search(query, timeout):
        captured.append(query)
        return []

    monkeypatch.setattr(discovery, "_provider_search", fake_provider_search)

    discovery.search_web_for_fields(
        identity,
        ["warranty"],
        limit=5,
        source_kind="MANUFACTURER_SUPPORT",
        category="PRINTER",
    )
    support_queries = list(captured)
    captured.clear()

    discovery.search_web_for_fields(
        identity,
        ["voltage"],
        limit=5,
        source_kind="CATEGORY_PROVIDER",
        category="ELECTRONIC_COMPONENT",
    )
    component_queries = list(captured)

    assert support_queries
    assert any("official support" in query.lower() for query in support_queries)
    assert component_queries
    assert any("component datasheet" in query.lower() or "technical distributor" in query.lower() for query in component_queries)


def test_matrix_has_required_generalization_breadth():
    brands = {row[0] for row in MATRIX}
    categories = {row[5] for row in MATRIX}
    assert len(MATRIX) >= 12
    assert len(brands) >= 12
    assert len(categories) >= 8
    assert "GENERAL" in categories
