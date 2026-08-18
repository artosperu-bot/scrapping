import fitz

from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_document_preflight import extract_verified_pdf_bytes


def _pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_sibling_pdf_is_rejected_before_full_extraction_callback_runs():
    identity = ProductIdentity(brand="JBL", model="Endurance Run 3 Wireless", variant="Wireless")
    calls = []

    def full_extract(*args, **kwargs):
        calls.append((args, kwargs))
        return "SHOULD NOT RUN", []

    result = extract_verified_pdf_bytes(
        identity,
        _pdf_bytes("JBL Endurance Run 3 Wired Sport Headphones. 3.5 mm audio cable."),
        "https://docs.example/JBL_Endurance_Run_3_Specsheet_EN.pdf",
        full_extract=full_extract,
    )

    assert result.match.relationship == "SIBLING_VARIANT"
    assert result.accepted is False
    assert result.text == ""
    assert result.evidence == ()
    assert calls == []


def test_exact_model_pdf_runs_full_extraction_only_after_preflight_acceptance():
    identity = ProductIdentity(brand="JBL", model="Endurance Run 3 Wireless", variant="Wireless")
    calls = []

    def full_extract(data, source_url, **kwargs):
        calls.append(source_url)
        return "FULL EXTRACTED TEXT", ["evidence"]

    result = extract_verified_pdf_bytes(
        identity,
        _pdf_bytes("JBL Endurance Run 3 Wireless. Bluetooth wireless sport headphones."),
        "https://docs.example/JBL_Endurance_Run_3_Wireless_Specsheet_EN.pdf",
        full_extract=full_extract,
    )

    assert result.match.relationship == "EXACT_MODEL"
    assert result.accepted is True
    assert result.text == "FULL EXTRACTED TEXT"
    assert result.evidence == ("evidence",)
    assert calls == ["https://docs.example/JBL_Endurance_Run_3_Wireless_Specsheet_EN.pdf"]
