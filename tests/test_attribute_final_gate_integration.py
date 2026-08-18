from product_intelligence.attribute_resolver import best_candidate
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord
from product_intelligence.semantic_guard import FieldContract


def _record(evidence):
    return ProductRecord(
        identity=ProductIdentity(brand="Example", model="Model X Wireless", match_level="EXACT", confidence=.99),
        evidence=[evidence],
    )


def _pdf_evidence(attribute, value, relationship="EXACT_MODEL", scope="MODEL", conflicts=None):
    return Evidence(
        attribute=attribute,
        raw_value=value,
        normalized_value=value,
        source_url="https://manufacturer.example/spec.pdf",
        source_type="official_pdf",
        match_level="EXACT",
        confidence=.99,
        identity_status="EXACT",
        authority="official_pdf",
        policy_allowed=True,
        document_relationship=relationship,
        document_scope=scope,
        hard_conflicts=list(conflicts or []),
    )


def test_attribute_resolver_does_not_select_sibling_pdf_fact():
    ev = _pdf_evidence("Weight", "250 g", relationship="SIBLING_VARIANT", scope="NONE")
    candidate = best_candidate(
        _record(ev),
        "Weight",
        None,
        "weight",
        FieldContract("weight", "product", "number", ("mass",), (), .99),
    )
    assert candidate is None


def test_attribute_resolver_does_not_select_model_scope_color_for_sku_field():
    ev = _pdf_evidence("Color", "Black")
    candidate = best_candidate(
        _record(ev),
        "Color",
        None,
        "color",
        FieldContract("color", "product", "text", (), (), .99),
    )
    assert candidate is None


def test_attribute_resolver_keeps_exact_model_technical_fact():
    ev = _pdf_evidence("Weight", "250 g")
    candidate = best_candidate(
        _record(ev),
        "Weight",
        None,
        "weight",
        FieldContract("weight", "product", "number", ("mass",), (), .99),
    )
    assert candidate is not None
    assert candidate.value == "250 g"
