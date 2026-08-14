from product_intelligence.canonical_facts import build_canonical_facts, canonical_invariant_errors
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord
from product_intelligence.smart_derivations import derive_autonomy, derive_connectivity, derive_power_source, derive_water_resistance


def ev(attr, value, source_type="manufacturer_html", confidence=.98):
    return Evidence(
        attribute=attr,
        raw_value=value,
        normalized_value=value,
        source_url="https://manufacturer.example/product",
        source_type=source_type,
        match_level="EXACT",
        confidence=confidence,
    )


def record(*evidence, **identity):
    return ProductRecord(identity=ProductIdentity(match_level="EXACT", confidence=.98, **identity), evidence=list(evidence))


def test_bluetooth_version_promotes_presence_and_wireless():
    rec = record(ev("Bluetooth", "5.4"), mpn="GEN-BT")
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["bluetooth"]["version"] == "5.4"
    assert facts["connectivity"]["bluetooth"]["present"] is True
    assert facts["connectivity"]["wireless"] is True
    assert canonical_invariant_errors(facts) == []


def test_connectivity_bluetooth_promotes_presence():
    rec = record(ev("Connectivity", "Bluetooth"), mpn="GEN-CONN")
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["bluetooth"]["present"] is True
    assert facts["connectivity"]["wireless"] is True


def test_ip65_promotes_independent_dust_and_water_components():
    rec = record(ev("IP Code", "IP65"), mpn="GEN-IP")
    facts = build_canonical_facts(rec)
    assert facts["durability"]["ip_rating"] == "IP65"
    assert facts["durability"]["dust_rating"] == 6
    assert facts["durability"]["water_rating"] == 5
    assert derive_water_resistance(rec, ["No", "IPX4", "IPX5", "IPX7"]).value == "IPX5"
    assert canonical_invariant_errors(facts) == []


def test_numeric_battery_life_and_rechargeable_yes_promote_battery_facts():
    rec = record(ev("Rechargeable battery", "Yes"), ev("Battery Life", "25"), mpn="GEN-BATT")
    facts = build_canonical_facts(rec)
    assert facts["battery"]["present"] is True
    assert facts["battery"]["rechargeable"] is True
    assert facts["battery"]["runtime_hours"] == 25
    assert derive_autonomy(rec).value is not None


def test_form_factor_and_sports_segment_promote_from_semantic_attributes():
    rec = record(ev("In-ear", "Yes"), ev("Activity", "Sports"), mpn="GEN-FORM")
    facts = build_canonical_facts(rec)
    assert facts["form_factor"] == "in-ear"
    assert facts["semantic_segment"] == "sports"


def test_gtin12_is_preserved_even_if_source_attribute_is_upc():
    rec = record(ev("UPC", "050036416887"), mpn="GEN-GTIN")
    facts = build_canonical_facts(rec)
    assert facts["identity"]["gtin"] == "050036416887"
    assert facts["identity"]["gtin_type"] == "GTIN-12"


def test_wired_usb_c_without_battery_maps_power_and_not_applicable_autonomy():
    rec = record(
        ev("Connectivity", "USB-C wired"),
        ev("Battery Required", "No"),
        mpn="GEN-USB-C",
    )
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["usb_c"] is True
    assert facts["connectivity"]["wired"] is True
    assert facts["connectivity"]["bluetooth"]["present"] is not True
    assert facts["battery"]["present"] is False
    assert derive_autonomy(rec).reason.startswith("NOT_APPLICABLE")
    assert derive_power_source(rec, ["USB", "Batería recargable"]).value == "USB"
    connectivity = derive_connectivity(rec, ["USB C", "Bluetooth", "Inalámbrico", "Alámbrico"])
    assert "USB C" in connectivity.value
    assert "Alámbrico" in connectivity.value
    assert "Bluetooth" not in connectivity.value
    assert "Inalámbrico" not in connectivity.value


def test_charging_usb_c_is_not_host_connectivity():
    rec = record(ev("Charging cable", "USB-C"), mpn="GEN-CHARGE")
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["usb_c"] is False
    assert facts["connectivity"]["wired"] is None
