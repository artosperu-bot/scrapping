from product_intelligence.description_narrator import build_safe_facts
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord


def _ev(attribute, value, confidence=.95):
    return Evidence(
        attribute=attribute,
        raw_value=value,
        normalized_value=value,
        source_url="https://example.com/product",
        source_type="manufacturer_html",
        match_level="EXACT",
        confidence=confidence,
    )


def test_unknown_bluetooth_never_enters_mistral_facts():
    rec = ProductRecord(
        identity=ProductIdentity(brand="JBL", model="Quantum 350", match_level="EXACT", confidence=.98),
        evidence=[_ev("Speakers", "Bluetooth")],
    )
    facts = build_safe_facts(rec)
    assert not any("bluetooth" in item.lower() for item in facts)


def test_mistral_facts_use_canonical_units_and_spanish_labels():
    rec = ProductRecord(
        identity=ProductIdentity(brand="JBL", model="Quantum 350", match_level="EXACT", confidence=.98),
        evidence=[_ev("Driver size", "40 mm"), _ev("Weight", "252 g")],
    )
    facts = build_safe_facts(rec)
    assert "Tamaño del driver: 40 mm" in facts
    assert "Peso: 252 g" in facts
    assert not any("Driver size" in item for item in facts)


def test_explicit_supported_bluetooth_can_enter_mistral_facts():
    rec = ProductRecord(
        identity=ProductIdentity(brand="JBL", model="Example", match_level="EXACT", confidence=.98),
        evidence=[_ev("Bluetooth", "Yes")],
    )
    facts = build_safe_facts(rec)
    assert "Bluetooth: Sí" in facts
