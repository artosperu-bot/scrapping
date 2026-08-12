from product_intelligence.batch import (
    _coverage_sufficient,
    _identity_placeholder,
    _looks_like_part_number,
    _promote_mpn,
)


def test_template_barcode_example_is_not_a_real_identity():
    assert _identity_placeholder("1234567890") is True


def test_alphanumeric_model_code_can_be_promoted_to_mpn():
    vals = {"model": "JBLQ350WLBLKAM"}
    _promote_mpn(vals)
    assert vals["mpn"] == "JBLQ350WLBLKAM"
    assert _looks_like_part_number("JBLQ350WLBLKAM") is True


def test_plain_product_name_is_not_promoted_to_mpn():
    vals = {"product_name": "JBL Quantum 350 Wireless"}
    _promote_mpn(vals)
    assert "mpn" not in vals


def test_research_does_not_stop_just_because_manufacturer_exists():
    resolution = {"blocked": False, "research_terms": ["battery life", "package weight"]}
    assert _coverage_sufficient(resolution, has_manufacturer=True) is False


def test_research_stops_only_when_coverage_is_sufficient():
    resolution = {"blocked": False, "research_terms": []}
    assert _coverage_sufficient(resolution, has_manufacturer=True) is True
    assert _coverage_sufficient(resolution, has_manufacturer=False) is False
