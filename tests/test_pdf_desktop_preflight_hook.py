from pathlib import Path

import fitz

from product_intelligence import pdf_desktop, pipeline
from product_intelligence.pdf_evidence import pdf_evidence_scope


def _pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_desktop_hooks_the_active_verified_pdf_bytes_path():
    assert pipeline.extract_pdf_bytes is pdf_desktop._scoped_extract_pdf_bytes
    # The old URL hook remains only for compatibility with existing desktop code.
    assert pipeline.extract_pdf is pdf_desktop._scoped_extract_pdf


def test_verified_bytes_hook_saves_existing_bytes_without_redownload(tmp_path, monkeypatch):
    data = _pdf_bytes("Example Model X Wireless technical specifications")
    source_url = "https://manufacturer.example/Model_X_Wireless_Spec.pdf"
    calls = []
    events = []

    def base_extract(payload, url, **kwargs):
        calls.append((payload, url, kwargs))
        return "FULL TEXT", []

    monkeypatch.setattr(pdf_desktop, "_BASE_EXTRACT_PDF_BYTES", base_extract)
    monkeypatch.setattr(
        pdf_desktop,
        "download_pdf",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not redownload verified bytes")),
    )

    with pdf_evidence_scope(enabled=True, output_root=str(tmp_path), event_sink=events.append):
        text, evidence = pdf_desktop._scoped_extract_pdf_bytes(
            data,
            source_url,
            match_level="EXACT",
            confidence=.96,
            parent_source_url="https://manufacturer.example/model-x-wireless",
        )

    assert text == "FULL TEXT"
    assert evidence == []
    assert calls and calls[0][0] == data
    saved = list((tmp_path / "pdf_evidence").glob("*.pdf"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == data
    stages = [event["stage"] for event in events]
    assert "PDF_DOWNLOADED" in stages
    assert "PDF_TEXT" in stages


def test_verified_bytes_hook_respects_pdf_disabled_scope(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pdf_desktop,
        "_BASE_EXTRACT_PDF_BYTES",
        lambda *args, **kwargs: (calls.append(True) or ("SHOULD NOT RUN", [])),
    )

    with pdf_evidence_scope(enabled=False):
        text, evidence = pdf_desktop._scoped_extract_pdf_bytes(
            _pdf_bytes("Example"),
            "https://manufacturer.example/example.pdf",
        )

    assert text == ""
    assert evidence == []
    assert calls == []
