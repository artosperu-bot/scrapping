from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_evidence import validate_pdf_identity


def test_known_brand_pdf_rejects_incidental_a_2794_text_without_brand_binding():
    identity = ProductIdentity(brand="Apple", mpn="A2794")
    text = "An Act relating to section A 2794 of the transportation code. Senate Bill 2794."

    match = validate_pdf_identity(identity, text, "https://capitol.example/bills/SB02794I.pdf")

    assert match.accepted is False


def test_known_brand_pdf_accepts_strong_identifier_when_brand_is_also_present():
    identity = ProductIdentity(brand="Apple", mpn="A2794")
    text = "Apple USB-C Charge Cable 240W. Model A2794. Technical specifications."

    match = validate_pdf_identity(identity, text, "https://manuals.example/apple-a2794.pdf")

    assert match.accepted is True
    assert match.reason in {"strong_identifier_brand", "brand_model"}


def test_unknown_brand_pdf_can_still_use_exact_strong_identifier():
    identity = ProductIdentity(mpn="ZX-4109")
    text = "Industrial sensor model ZX-4109 technical datasheet."

    match = validate_pdf_identity(identity, text, "https://docs.example/zx-4109.pdf")

    assert match.accepted is True
