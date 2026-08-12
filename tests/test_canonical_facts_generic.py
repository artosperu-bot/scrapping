from product_intelligence.canonical_facts import build_canonical_facts
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord
from product_intelligence.smart_derivations import derive_connectivity, derive_power_source


def evidence(attr, value):
    return Evidence(attribute=attr, raw_value=value, normalized_value=value, source_type="official_html", match_level="EXACT", confidence=.96)


def record(*rows):
    return ProductRecord(identity=ProductIdentity(mpn="GENERIC", match_level="EXACT", confidence=.9), evidence=list(rows))


def test_laptop_connectivity_facts():
    facts=build_canonical_facts(record(evidence("Bluetooth Version","5.2"), evidence("Wireless","Wi-Fi 6"), evidence("Processor","Intel Core i5-13420H")))
    assert facts["connectivity"]["bluetooth"]["present"] is True
    assert facts["connectivity"]["bluetooth"]["version"] == "5.2"
    assert facts["connectivity"]["wifi"] is True


def test_ssd_interface_does_not_create_wireless_facts():
    facts=build_canonical_facts(record(evidence("Interface","PCIe 4.0 x4 NVMe M.2 2280")))
    assert facts["connectivity"]["bluetooth"]["present"] is None
    assert facts["connectivity"]["wireless"] is None


def test_smartphone_ip_rating_is_decomposed():
    facts=build_canonical_facts(record(evidence("IP Rating","IP68"), evidence("Battery Capacity","6320 mAh")))
    assert facts["durability"]["ip_rating"] == "IP68"
    assert facts["durability"]["dust_rating"] == 6
    assert facts["durability"]["water_rating"] == 8


def test_wired_usb_c_without_battery_maps_safely():
    r=record(evidence("Connection Type","Wired USB-C"), evidence("Battery","No battery"))
    assert derive_connectivity(r,["USB-C","Bluetooth","Inalámbrico","Alámbrico"]).value == "USB-C, Alámbrico"
    assert derive_power_source(r,["Batería recargable","USB"]).value == "USB"
