from product_intelligence.models import Evidence, ProductIdentity, ProductRecord
from product_intelligence.resolution_engine import analyze_resolution, NOT_APPLICABLE
from product_intelligence.smart_derivations import derive_autonomy, derive_water_resistance


def _rec(evidence):
    return ProductRecord(
        identity=ProductIdentity(mpn="X1", match_level="EXACT", confidence=.99),
        evidence=evidence,
    )


def test_wired_without_battery_marks_autonomy_not_applicable():
    rec=_rec([
        Evidence(attribute="connection type", raw_value="Wired USB-C", normalized_value="Wired USB-C", source_type="official_html", match_level="EXACT", confidence=.95),
        Evidence(attribute="battery", raw_value="No battery", normalized_value="No battery", source_type="official_html", match_level="EXACT", confidence=.95),
    ])
    audit=analyze_resolution(rec,{"scrape_semantics":["Autonomía"]})
    assert audit["fields"][0]["status"] == NOT_APPLICABLE
    derived=derive_autonomy(rec)
    assert derived.value is None
    assert derived.reason.startswith("NOT_APPLICABLE")


def test_ip65_projects_water_component_to_ipx5_when_allowed():
    rec=_rec([
        Evidence(attribute="IP rating", raw_value="IP65", normalized_value="IP65", source_type="official_html", match_level="EXACT", confidence=.98),
    ])
    derived=derive_water_resistance(rec,["No","IPX4","IPX5","IPX7"])
    assert derived.value == "IPX5"
    assert derived.reason.startswith("FOUND_DERIVED")


def test_missing_field_is_sent_to_gap_research():
    rec=_rec([
        Evidence(attribute="Bluetooth", raw_value="5.3", normalized_value="5.3", source_type="official_html", match_level="EXACT", confidence=.95),
    ])
    audit=analyze_resolution(rec,{"scrape_semantics":["Bluetooth","Package weight"]})
    assert "Package weight" in audit["research_terms"]
    assert any(x["semantic"] == "Bluetooth" and x["status"] == "FOUND_DIRECT" for x in audit["fields"])
