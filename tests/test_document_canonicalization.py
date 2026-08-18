from product_intelligence.document_canonicalization import (
    DocumentVariant,
    canonical_coverage_count,
    group_document_variants,
)


def _variant(name: str, *, document_type: str = "SPEC_SHEET", relationship: str = "EXACT_MODEL"):
    return DocumentVariant(
        url=f"https://support.example/{name}",
        title=name,
        product_key="JBL Quantum 350 Wireless",
        document_type=document_type,
        relationship=relationship,
    )


def test_four_languages_of_same_specsheet_are_one_canonical_document():
    variants = [
        _variant("JBL_Quantum_350_Wireless_Specsheet_EN.pdf"),
        _variant("JBL_Quantum_350_Wireless_Specsheet_DE.pdf"),
        _variant("JBL_Quantum_350_Wireless_Specsheet_NL.pdf"),
        _variant("JBL_Quantum_350_Wireless_Specsheet_DA.pdf"),
    ]

    groups = group_document_variants(variants)

    assert len(groups) == 1
    assert groups[0].unique_document_count == 1
    assert groups[0].language_variant_count == 4
    assert {item.language for item in groups[0].variants} == {"EN", "DE", "NL", "DA"}
    assert groups[0].preferred.language == "EN"
    assert canonical_coverage_count(variants) == 1


def test_spanish_is_preferred_over_english_when_both_exist():
    variants = [
        _variant("JBL_Quantum_350_Wireless_Specsheet_EN.pdf"),
        _variant("JBL_Quantum_350_Wireless_Specsheet_ES.pdf"),
        _variant("JBL_Quantum_350_Wireless_Specsheet_DE.pdf"),
    ]

    groups = group_document_variants(variants)

    assert len(groups) == 1
    assert groups[0].preferred.language == "ES"


def test_language_names_and_ptbr_suffixes_are_normalized():
    variants = [
        _variant("Model_X_Specification_Sheet_English.pdf"),
        _variant("Model_X_Specification_Sheet_German.pdf"),
        _variant("Model_X_Specification_Sheet_PTBR.pdf"),
    ]
    variants = [item.__class__(**{**item.__dict__, "product_key": "Model X"}) for item in variants]

    groups = group_document_variants(variants)

    assert len(groups) == 1
    assert {item.language for item in groups[0].variants} == {"EN", "DE", "PT-BR"}


def test_manual_and_specsheet_remain_distinct_documents():
    variants = [
        _variant("JBL_Quantum_350_Wireless_Specsheet_EN.pdf", document_type="SPEC_SHEET"),
        _variant("JBL_Quantum_350_Wireless_Owners_Manual_EN.pdf", document_type="MANUAL"),
    ]

    groups = group_document_variants(variants)

    assert len(groups) == 2
    assert canonical_coverage_count(variants) == 2


def test_different_product_keys_never_collapse_into_same_document():
    a = _variant("Endurance_Run_3_Wireless_Specsheet_EN.pdf")
    b = _variant("Endurance_Run_3C_USB-C_Specsheet_EN.pdf")
    a = a.__class__(**{**a.__dict__, "product_key": "Endurance Run 3 Wireless"})
    b = b.__class__(**{**b.__dict__, "product_key": "Endurance Run 3C USB-C"})

    groups = group_document_variants([a, b])

    assert len(groups) == 2


def test_non_exact_relationships_do_not_count_as_document_coverage():
    exact = _variant("Model_X_Specsheet_EN.pdf")
    sibling = _variant("Model_X_Wired_Specsheet_EN.pdf", relationship="SIBLING_VARIANT")
    exact = exact.__class__(**{**exact.__dict__, "product_key": "Model X"})
    sibling = sibling.__class__(**{**sibling.__dict__, "product_key": "Model X"})

    assert canonical_coverage_count([exact, sibling]) == 1


def test_unknown_language_can_group_when_canonical_identity_and_type_match():
    variants = [
        _variant("Model_X_Specification_Sheet.pdf"),
        _variant("Model_X_Specification_Sheet_EN.pdf"),
    ]
    variants = [item.__class__(**{**item.__dict__, "product_key": "Model X"}) for item in variants]

    groups = group_document_variants(variants)

    assert len(groups) == 1
    assert groups[0].language_variant_count == 2
    assert groups[0].preferred.language == "EN"
