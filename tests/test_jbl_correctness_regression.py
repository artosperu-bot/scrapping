from product_intelligence.canonical_facts import build_canonical_facts
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord
from product_intelligence.resolution_engine import FOUND_DIRECT, INSUFFICIENT_EVIDENCE, analyze_resolution


def _ev(attribute, value, confidence=0.95, source_type="manufacturer_html"):
    return Evidence(
        attribute=attribute,
        raw_value=value,
        normalized_value=value,
        source_type=source_type,
        source_url="https://example.com/product",
        match_level="EXACT",
        confidence=confidence,
    )


def _record(*evidence, **identity):
    return ProductRecord(
        identity=ProductIdentity(match_level="EXACT", confidence=0.98, **identity),
        evidence=list(evidence),
    )


def test_quantum350_unknown_bluetooth_does_not_become_true():
    rec = _record(_ev("Speakers", "Bluetooth", 0.90), brand="JBL", model="Quantum 350")
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["bluetooth"]["present"] is None


def test_bluetooth_frequency_does_not_create_proprietary_rf():
    rec = _record(_ev("Bluetooth transmission frequency", "2.4 GHz", 0.95), brand="JBL", model="Endurance Run 3")
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["rf_2_4ghz"] is False


def test_charging_usb_c_does_not_create_wired_audio():
    rec = _record(_ev("Charging cable", "USB-C", 0.95), brand="JBL", model="Quantum 350")
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["wired"] is None
    assert facts["connectivity"]["usb_c"] is False


def test_gtin_brand_model_canonical_resolve_before_insufficient():
    rec = _record(brand="JBL", model="JBLT530CBLKAM", gtin="050036416887")
    plan = {"scrape_semantics": ["Marca", "Modelo", "Código de barras"]}
    result = analyze_resolution(rec, plan)
    by_name = {row["semantic"]: row for row in result["fields"]}
    assert by_name["Marca"]["status"] != INSUFFICIENT_EVIDENCE
    assert by_name["Modelo"]["status"] != INSUFFICIENT_EVIDENCE
    assert by_name["Código de barras"]["status"] == FOUND_DIRECT


def test_tune530c_usb_c_wired_stays_supported():
    rec = _record(_ev("Connectivity", "USB-C wired", 0.95), brand="JBL", model="JBLT530CBLKAM")
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["usb_c"] is True
    assert facts["connectivity"]["wired"] is True


def test_ip_conflict_does_not_use_last_value_seen():
    rec = _record(
        _ev("Ingress Protection", "IP65", 0.95, "official_manual"),
        _ev("IP rating", "IPX5", 0.80, "retailer"),
        brand="JBL",
        model="Endurance Run 3",
    )
    facts = build_canonical_facts(rec)
    assert facts["durability"]["ip_rating"] == "IP65"


def test_runtime_requires_canonical_resolution():
    rec = _record(
        _ev("Battery life", "25", 0.55, "secondary_html"),
        brand="JBL",
        model="Endurance Run 3",
    )
    plan = {"scrape_semantics": ["Autonomía"]}
    result = analyze_resolution(rec, plan)
    row = result["fields"][0]
    assert row["status"] == INSUFFICIENT_EVIDENCE
    assert result["canonical_facts"]["battery"]["runtime_hours"] is None
