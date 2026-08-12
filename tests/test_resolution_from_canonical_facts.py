from product_intelligence.models import Evidence, ProductIdentity, ProductRecord
from product_intelligence.resolution_engine import analyze_resolution


def ev(attr, value):
    return Evidence(
        attribute=attr,
        raw_value=value,
        normalized_value=value,
        source_url="https://manufacturer.example/product",
        source_type="manufacturer_html",
        match_level="EXACT",
        confidence=.98,
    )


def statuses(rec, semantics):
    result = analyze_resolution(rec, {"scrape_semantics": semantics})
    return {x["semantic"]: x["status"] for x in result["fields"]}, result


def test_known_bluetooth_ip_runtime_and_form_factor_never_end_insufficient():
    rec = ProductRecord(
        identity=ProductIdentity(mpn="GEN-SEM", match_level="EXACT", confidence=.98),
        evidence=[
            ev("Bluetooth", "5.4"),
            ev("IP Code", "IP65"),
            ev("Rechargeable battery", "Yes"),
            ev("Battery Life", "25"),
            ev("In-ear", "Yes"),
        ],
    )
    st, result = statuses(rec, ["bluetooth", "water resistance", "battery life", "headphone type"])
    assert st["bluetooth"] != "INSUFFICIENT_EVIDENCE"
    assert st["water resistance"] != "INSUFFICIENT_EVIDENCE"
    assert st["battery life"] != "INSUFFICIENT_EVIDENCE"
    assert st["headphone type"] != "INSUFFICIENT_EVIDENCE"
    assert result["canonical_invariant_errors"] == []


def test_exact_upc_resolves_barcode_semantic():
    rec = ProductRecord(
        identity=ProductIdentity(mpn="GEN-GTIN", match_level="EXACT", confidence=.98),
        evidence=[ev("UPC", "050036416887")],
    )
    st, _ = statuses(rec, ["barcode"])
    assert st["barcode"] == "FOUND_DIRECT"


def test_usb_c_wired_no_battery_marks_autonomy_not_applicable_and_power_resolvable():
    rec = ProductRecord(
        identity=ProductIdentity(mpn="GEN-WIRED", match_level="EXACT", confidence=.98),
        evidence=[ev("Connectivity", "USB-C wired"), ev("Battery Required", "No")],
    )
    st, _ = statuses(rec, ["battery life", "power source", "connectivity"])
    assert st["battery life"] == "NOT_APPLICABLE"
    assert st["power source"] != "INSUFFICIENT_EVIDENCE"
    assert st["connectivity"] != "INSUFFICIENT_EVIDENCE"
