from pathlib import Path

import fitz

from product_intelligence.document_discovery import DocumentProvenance
from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_evidence import validate_pdf_identity


def _write_pdf(path: Path, text: str) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    return path


def test_pdf_identity_exposes_exact_sku_relationship():
    identity = ProductIdentity(brand="Apple", model="USB-C Charge Cable 240W", mpn="A2794")
    match = validate_pdf_identity(
        identity,
        "Apple USB-C Charge Cable 240W. Model A2794. Technical specifications.",
        "https://manuals.example/apple-a2794.pdf",
    )

    assert match.accepted is True
    assert match.relationship == "EXACT_SKU"
    assert match.document_scope == "SKU"
    assert match.hard_conflicts == ()


def test_pdf_identity_exposes_exact_model_relationship():
    identity = ProductIdentity(brand="JBL", model="Endurance Run 3 Wireless", variant="Wireless")
    match = validate_pdf_identity(
        identity,
        "JBL Endurance Run 3 Wireless sport headphones. Bluetooth wireless audio.",
        "https://docs.example/endurance-run-3-wireless-spec.pdf",
    )

    assert match.accepted is True
    assert match.relationship == "EXACT_MODEL"
    assert match.document_scope == "MODEL"


def test_pdf_identity_classifies_wired_endurance_as_sibling_variant():
    identity = ProductIdentity(brand="JBL", model="Endurance Run 3 Wireless", variant="Wireless")
    match = validate_pdf_identity(
        identity,
        "JBL Endurance Run 3 Wired Sport Headphones. 3.5 mm audio cable.",
        "https://docs.example/JBL_Endurance_Run_3_Specsheet_EN.pdf",
    )

    assert match.accepted is False
    assert match.relationship == "SIBLING_VARIANT"
    assert match.hard_conflicts
    assert any("connectivity" in item.lower() for item in match.hard_conflicts)


def test_manufacturer_provenance_cannot_override_sibling_hard_conflict(tmp_path, monkeypatch):
    from product_intelligence import pdf_review

    source = _write_pdf(
        tmp_path / "wired.pdf",
        "JBL Endurance Run 3 Wired Sport Headphones. 3.5 mm audio cable.",
    )

    class Downloaded:
        path = source
        source_url = "https://support.example/wired.pdf"
        final_url = "https://support.example/wired.pdf"
        content_type = "application/pdf"
        size_bytes = source.stat().st_size
        sha256 = "sibling"

    monkeypatch.setattr(pdf_review, "download_pdf", lambda *args, **kwargs: Downloaded())

    provenance = DocumentProvenance(
        parent_url="https://manufacturer.example/endurance-run-3-wireless",
        parent_identity_status="EXACT",
        parent_identity_confidence=0.99,
        parent_authority="MANUFACTURER",
        anchor_text="Specifications",
    )
    identity = ProductIdentity(brand="JBL", model="Endurance Run 3 Wireless", variant="Wireless")

    result = pdf_review.inspect_pdf_candidate(
        identity,
        Downloaded.final_url,
        tmp_path / "cache",
        provenance=provenance,
    )

    assert result.identity_accepted is False
    assert result.identity_provenance_bound is False
    assert result.selection_allowed is False
    assert "conflict" in result.identity_reason.lower() or "sibling" in result.identity_reason.lower()
