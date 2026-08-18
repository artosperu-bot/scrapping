from product_intelligence.final_evidence_gate import evaluate_field_write
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord


def _record(match_level="EXACT"):
    return ProductRecord(identity=ProductIdentity(brand="JBL", model="Endurance Run 3 Wireless", match_level=match_level, confidence=.99))


def _evidence(**updates):
    data = dict(
        attribute="Battery life",
        raw_value="10 h",
        normalized_value="10 h",
        source_url="https://example.com/spec.pdf",
        source_type="official_pdf",
        match_level="EXACT",
        confidence=.97,
        identity_status="EXACT",
        authority="official_pdf",
        policy_allowed=True,
        document_relationship="EXACT_MODEL",
        document_scope="MODEL",
        hard_conflicts=[],
    )
    data.update(updates)
    return Evidence(**data)


def test_exact_model_document_can_write_model_level_technical_field():
    decision = evaluate_field_write(_record(), "battery life", _evidence())
    assert decision.allowed is True
    assert decision.reason == "EVIDENCE_PROVEN_FOR_FIELD"


def test_exact_model_document_cannot_prove_sku_sensitive_color():
    decision = evaluate_field_write(
        _record(),
        "color",
        _evidence(attribute="Color", raw_value="Black", normalized_value="Black"),
    )
    assert decision.allowed is False
    assert decision.reason == "MODEL_SCOPE_CANNOT_PROVE_SKU_FIELD"


def test_exact_sku_document_can_prove_sku_sensitive_color():
    decision = evaluate_field_write(
        _record(),
        "color",
        _evidence(
            attribute="Color",
            raw_value="Black",
            normalized_value="Black",
            document_relationship="EXACT_SKU",
            document_scope="SKU",
        ),
    )
    assert decision.allowed is True


def test_sibling_document_is_never_write_eligible():
    decision = evaluate_field_write(
        _record(),
        "battery life",
        _evidence(document_relationship="SIBLING_VARIANT", document_scope="NONE"),
    )
    assert decision.allowed is False
    assert decision.reason == "DOCUMENT_RELATIONSHIP_NOT_EXACT"


def test_hard_conflict_vetoes_otherwise_exact_document():
    decision = evaluate_field_write(
        _record(),
        "battery life",
        _evidence(hard_conflicts=["connectivity mismatch: Wireless != Wired"]),
    )
    assert decision.allowed is False
    assert decision.reason == "UNRESOLVED_HARD_CONFLICT"


def test_upstream_policy_rejection_cannot_be_overridden_at_excel_boundary():
    decision = evaluate_field_write(_record(), "battery life", _evidence(policy_allowed=False))
    assert decision.allowed is False
    assert decision.reason == "EVIDENCE_POLICY_REJECTED"


def test_record_identity_conflict_blocks_field_write():
    decision = evaluate_field_write(_record("CONFLICT"), "battery life", _evidence())
    assert decision.allowed is False
    assert decision.reason == "PRODUCT_IDENTITY_NOT_VALID"


def test_non_pdf_legacy_evidence_remains_supported_when_identity_and_policy_are_valid():
    evidence = Evidence(
        attribute="Weight",
        raw_value="250 g",
        normalized_value="250 g",
        source_url="https://manufacturer.example/product",
        source_type="official_html",
        match_level="EXACT",
        confidence=.95,
        identity_status="EXACT",
        authority="manufacturer",
        policy_allowed=True,
    )
    decision = evaluate_field_write(_record(), "weight", evidence)
    assert decision.allowed is True
