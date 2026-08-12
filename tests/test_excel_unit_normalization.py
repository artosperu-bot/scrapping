from product_intelligence.attribute_resolver import normalize_value_for_excel
from product_intelligence.semantic_guard import FieldContract


def test_package_weight_is_converted_to_kg_number_when_excel_declares_kilos():
    contract = FieldContract(
        semantic="package_weight",
        context="package",
        value_type="number",
        allowed_dimensions=("mass",),
        confidence=.99,
    )
    value, reason = normalize_value_for_excel(
        "0.72 lb",
        "Ingresa el peso del producto embalado, el número se tomará como kilos. // The number will be taken as kilograms.",
        contract,
    )
    assert abs(float(value) - 0.3265865064) < 1e-6
    assert reason == "normalized_lb_to_kg_for_excel"


def test_package_length_is_converted_to_cm_number_when_excel_declares_centimeters():
    contract = FieldContract(
        semantic="package_length",
        context="package",
        value_type="dimension",
        allowed_dimensions=("length",),
        confidence=.99,
    )
    value, reason = normalize_value_for_excel(
        "10 in",
        "Ingresa el largo del producto embalado, el número se tomará como centímetros. // The number will be taken as centimeters.",
        contract,
    )
    assert value == 25.4
    assert reason == "normalized_in_to_cm_for_excel"


def test_no_conversion_when_excel_does_not_declare_target_unit():
    contract = FieldContract(
        semantic="weight",
        context="product",
        value_type="number",
        allowed_dimensions=("mass",),
    )
    value, reason = normalize_value_for_excel("252 g", "Peso del producto", contract)
    assert value == "252 g"
    assert reason is None
