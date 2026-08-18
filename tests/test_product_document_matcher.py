from product_intelligence.models import ProductIdentity
from product_intelligence.product_document_matcher import (
    DocumentFingerprint,
    ProductDocumentMatcher,
    ProductFingerprint,
)


def _match(identity: ProductIdentity, *, title: str, text: str = "", url: str = "https://docs.example/spec.pdf"):
    product = ProductFingerprint.from_identity(identity)
    document = DocumentFingerprint.from_evidence(url=url, title=title, text=text)
    return ProductDocumentMatcher().match(product, document)


def test_exact_mpn_is_exact_sku():
    result = _match(
        ProductIdentity(brand="Apple", model="USB-C Charge Cable 240W", mpn="A2794"),
        title="Apple USB-C Charge Cable 240W Technical Specifications",
        text="Apple. Model A2794. USB-C Charge Cable (240W).",
    )

    assert result.relationship == "EXACT_SKU"
    assert result.accepted is True
    assert result.document_scope == "SKU"
    assert any("A2794" in item for item in result.positive_evidence)


def test_exact_functional_model_is_exact_model_without_literal_mpn():
    result = _match(
        ProductIdentity(brand="JBL", model="Endurance Run 3 Wireless", variant="Wireless"),
        title="JBL Endurance Run 3 Wireless Spec Sheet",
        text="JBL Endurance Run 3 Wireless sport headphones. Bluetooth wireless audio.",
    )

    assert result.relationship == "EXACT_MODEL"
    assert result.accepted is True
    assert result.document_scope == "MODEL"
    assert result.hard_conflicts == ()


def test_wireless_target_rejects_wired_sibling_even_with_family_overlap():
    result = _match(
        ProductIdentity(brand="JBL", model="Endurance Run 3 Wireless", variant="Wireless"),
        title="JBL Endurance Run 3 Spec Sheet",
        text="JBL Endurance Run 3 Wired Sport Headphones. 3.5 mm audio cable.",
    )

    assert result.relationship == "SIBLING_VARIANT"
    assert result.accepted is False
    assert any("connectivity" in conflict.lower() for conflict in result.hard_conflicts)


def test_wireless_target_rejects_usb_c_wired_sibling():
    result = _match(
        ProductIdentity(brand="JBL", model="Endurance Run 3 Wireless", variant="Wireless"),
        title="JBL Endurance Run 3C USB-C Spec Sheet",
        text="JBL Endurance Run 3C USB-C Wired Sport Headphones.",
    )

    assert result.relationship == "SIBLING_VARIANT"
    assert result.accepted is False
    assert result.hard_conflicts


def test_family_name_without_discriminating_variant_is_not_exact_model():
    result = _match(
        ProductIdentity(brand="JBL", model="Endurance Run 3 Wireless", variant="Wireless"),
        title="JBL Endurance Run 3 Documentation",
        text="JBL Endurance Run 3 product information.",
    )

    assert result.relationship in {"RELATED_FAMILY", "UNKNOWN"}
    assert result.accepted is False


def test_numeric_model_collision_is_not_accepted():
    result = _match(
        ProductIdentity(brand="Brother", model="HL-L2460DW"),
        title="Brother HL-L2480DW User Guide",
        text="Brother HL-L2480DW monochrome laser printer user guide.",
    )

    assert result.relationship in {"SIBLING_VARIANT", "RELATED_FAMILY"}
    assert result.accepted is False
    assert result.hard_conflicts


def test_general_non_jbl_generation_conflict_vetoes_family_similarity():
    result = _match(
        ProductIdentity(brand="Lenovo", model="ThinkPad T14 Gen 5", variant="Gen 5"),
        title="ThinkPad T14 Gen 4 Product Specifications",
        text="Lenovo ThinkPad T14 Gen 4 technical specifications.",
    )

    assert result.relationship == "SIBLING_VARIANT"
    assert result.accepted is False
    assert any("generation" in conflict.lower() for conflict in result.hard_conflicts)


def test_brand_conflict_is_unrelated_even_when_model_number_text_overlaps():
    result = _match(
        ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM"),
        title="Hot Wheels JBL03 Product Sheet",
        text="Mattel Hot Wheels JBL03 toy vehicle.",
    )

    assert result.relationship == "UNRELATED"
    assert result.accepted is False
