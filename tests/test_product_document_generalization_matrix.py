import pytest

from product_intelligence.models import ProductIdentity
from product_intelligence.product_document_matcher import (
    DocumentFingerprint,
    ProductDocumentMatcher,
    ProductFingerprint,
)


# Deterministic QA fixtures built from real product identifiers/models already used
# by the project's cross-brand identity benchmark. They are test oracles, not a
# replacement for live manufacturer evidence.
CASES = [
    ("accessory", ProductIdentity(brand="Apple", model="USB-C Charge Cable 240W", mpn="A2794"), "Apple USB-C Charge Cable 240W. Model A2794 technical specifications."),
    ("smartphone", ProductIdentity(brand="Samsung", model="Galaxy S24 Ultra", mpn="SM-S928B"), "Samsung Galaxy S24 Ultra. Model SM-S928B specifications."),
    ("mouse", ProductIdentity(brand="Logitech", mpn="910-006556"), "Logitech product. Part number 910-006556."),
    ("headphones", ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM"), "JBL Quantum 350 Wireless. JBLQ350WLBLKAM specification sheet."),
    ("laptop", ProductIdentity(brand="Lenovo", model="V15 G4 IRU"), "Lenovo V15 G4 IRU product specifications."),
    ("ssd", ProductIdentity(brand="Kingston", model="NV2", mpn="SNV2S/1000G"), "Kingston NV2 PCIe SSD. Part number SNV2S/1000G."),
    ("networking", ProductIdentity(brand="TP-Link", model="Archer AX55"), "TP-Link Archer AX55 wireless router datasheet."),
    ("monitor", ProductIdentity(brand="Dell", model="P2422H"), "Dell P2422H monitor specifications."),
    ("printer", ProductIdentity(brand="Brother", model="HL-L2460DW"), "Brother HL-L2460DW monochrome laser printer specifications."),
    ("headphones", ProductIdentity(brand="Sony", model="WH-1000XM5"), "Sony WH-1000XM5 wireless noise cancelling headphones help guide."),
    ("printer", ProductIdentity(brand="Epson", model="L3250"), "Epson L3250 multifunction printer technical specifications."),
    ("smartphone", ProductIdentity(brand="Ulefone", model="Armor 22"), "Ulefone Armor 22 rugged smartphone specifications."),
]

SIBLING_TRAPS = [
    (ProductIdentity(brand="Samsung", model="Galaxy S24 Ultra SM-S928B"), "Samsung Galaxy S24 SM-S921B specifications."),
    (ProductIdentity(brand="Lenovo", model="V15 G4 IRU"), "Lenovo V15 G3 IRU product specifications."),
    (ProductIdentity(brand="Kingston", model="NV2 SNV2S/1000G"), "Kingston NV2 SNV2S/2000G product sheet."),
    (ProductIdentity(brand="TP-Link", model="Archer AX55"), "TP-Link Archer AX53 wireless router datasheet."),
    (ProductIdentity(brand="Brother", model="HL-L2460DW"), "Brother HL-L2480DW monochrome laser printer guide."),
]


def _match(identity, text):
    return ProductDocumentMatcher().match(
        ProductFingerprint.from_identity(identity),
        DocumentFingerprint.from_evidence(url="https://fixture.example/document.pdf", text=text),
    )


def test_generalization_matrix_has_required_brand_and_category_diversity():
    brands = {identity.brand for _category, identity, _text in CASES}
    categories = {category for category, _identity, _text in CASES}
    assert len(CASES) >= 12
    assert len(brands) >= 5
    assert len(categories) >= 5
    assert len(brands) == 12
    assert len(categories) >= 7


@pytest.mark.parametrize("category,identity,text", CASES)
def test_real_cross_brand_exact_documents_are_accepted(category, identity, text):
    result = _match(identity, text)
    assert result.relationship in {"EXACT_SKU", "EXACT_MODEL"}, (category, identity, result)
    assert result.accepted is True
    assert result.hard_conflicts == ()


@pytest.mark.parametrize("identity,text", SIBLING_TRAPS)
def test_cross_brand_sibling_model_collisions_are_rejected(identity, text):
    result = _match(identity, text)
    assert result.accepted is False
    assert result.relationship in {"SIBLING_VARIANT", "RELATED_FAMILY", "UNKNOWN"}
    assert result.hard_conflicts or result.relationship in {"RELATED_FAMILY", "UNKNOWN"}
