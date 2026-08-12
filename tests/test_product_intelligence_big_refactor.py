from product_intelligence.identifiers import possible_identifier_typo, validate_gtin
from product_intelligence.marketplace_resolution import FOUND_DIRECT, FOUND_MAPPED, resolve_marketplace_field
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord
from product_intelligence.record_builder import build_record_strict
from product_intelligence.semantic_guard import FieldContract


def _ev(attribute, value, source_type, source="https://example.test/product", confidence=.95):
    return Evidence(
        attribute=attribute,
        raw_value=value,
        normalized_value=value,
        source_url=source,
        source_type=source_type,
        match_level="EXACT",
        confidence=confidence,
    )


def test_gtin_checksum_validation_supports_upc_and_ean():
    assert validate_gtin("050036416887").valid
    assert validate_gtin("4006381333931").valid
    assert not validate_gtin("4006381333932").valid


def test_part_number_typo_is_warning_only():
    result = possible_identifier_typo("ABC12345", "ABC12354")
    assert result is not None
    assert result["code"] == "possible_part_number_typo"
    assert result["auto_confirm"] is False


def test_manufacturer_fact_wins_over_secondary_for_same_canonical_field():
    rec = build_record_strict(
        ProductIdentity(mpn="GEN-1", match_level="EXACT", confidence=.9),
        [
            _ev("Color", "Blue", "secondary_html", "https://shop.example/item", .99),
            _ev("Color", "Black", "manufacturer_html", "https://maker.example/item", .90),
        ],
        ["https://shop.example/item", "https://maker.example/item"],
    )
    assert rec.specifications["color"]["value"] == "Black"
    assert rec.specifications["color"]["source_family"] == "manufacturer"


def test_field_resolution_maps_before_writer():
    rec = ProductRecord(
        identity=ProductIdentity(brand="Example", mpn="GEN-2", match_level="EXACT", confidence=.95),
        evidence=[],
    )
    contract = FieldContract(semantic="brand", value_type="controlled")
    result = resolve_marketplace_field(
        rec,
        header="Marca #26",
        description="Select a brand from list",
        canonical="brand",
        contract=contract,
        options=["Example", "Other"],
    )
    assert result.status in {FOUND_DIRECT, FOUND_MAPPED}
    assert result.value == "Example"
    assert result.source == "identity"


def test_resolution_returns_no_value_for_unknown_fact_instead_of_inventing():
    rec = ProductRecord(identity=ProductIdentity(mpn="GEN-3", match_level="EXACT", confidence=.95))
    result = resolve_marketplace_field(
        rec,
        header="Peso del paquete",
        description="Peso del producto embalado",
        canonical="package weight",
        contract=FieldContract(semantic="package weight", context="package", value_type="number", allowed_dimensions=("mass",)),
        options=[],
    )
    assert result.value is None
    assert result.status == "INSUFFICIENT_EVIDENCE"


def test_invalid_standard_gtin_never_reaches_excel_writer():
    rec = ProductRecord(
        identity=ProductIdentity(ean="4006381333932", mpn="GEN-4", match_level="EXACT", confidence=.95),
    )
    result = resolve_marketplace_field(
        rec,
        header="Código de barras #56",
        description="Universal product barcode",
        canonical="ean",
        contract=FieldContract(semantic="ean", value_type="number"),
        options=[],
    )
    assert result.value is None
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.reason.startswith("INVALID_GTIN-13")


def test_valid_upc_can_reach_barcode_field():
    rec = ProductRecord(
        identity=ProductIdentity(upc="050036416887", mpn="GEN-5", match_level="EXACT", confidence=.95),
    )
    result = resolve_marketplace_field(
        rec,
        header="Código de barras #56",
        description="Universal product barcode",
        canonical="upc",
        contract=FieldContract(semantic="upc", value_type="number"),
        options=[],
    )
    assert result.value == "050036416887"
    assert result.status == FOUND_DIRECT
