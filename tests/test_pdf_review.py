from pathlib import Path

import fitz

from product_intelligence.models import ProductIdentity


def _write_pdf(path: Path, text: str) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    return path


def test_inspect_pdf_candidate_validates_identity_and_renders_preview(tmp_path, monkeypatch):
    from product_intelligence import pdf_review

    source = _write_pdf(
        tmp_path / "source.pdf",
        "JBL Quantum 350 Wireless JBLQ350WLBLKAM\nDriver size 40 mm\nBattery life 22 hours",
    )

    class Downloaded:
        path = source
        source_url = "https://example.test/q350.pdf"
        final_url = "https://example.test/q350.pdf"
        content_type = "application/pdf"
        size_bytes = source.stat().st_size
        sha256 = "abc"

    monkeypatch.setattr(pdf_review, "download_pdf", lambda *args, **kwargs: Downloaded())
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")

    result = pdf_review.inspect_pdf_candidate(identity, Downloaded.final_url, tmp_path / "cache")

    assert result.identity_accepted is True
    assert result.identity_pending_ocr is False
    assert result.identity_confidence >= 0.90
    assert result.page_count == 1
    assert result.native_text_chars > 30
    assert result.ocr_recommended is False
    assert result.preview_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert result.local_path.is_file()


def test_inspect_pdf_candidate_recommends_ocr_for_low_text_but_known_identity(tmp_path, monkeypatch):
    from product_intelligence import pdf_review

    source = _write_pdf(tmp_path / "image-like.pdf", "JBL JBLQ350WLBLKAM")

    class Downloaded:
        path = source
        source_url = "https://example.test/scan.pdf"
        final_url = "https://example.test/scan.pdf"
        content_type = "application/pdf"
        size_bytes = source.stat().st_size
        sha256 = "def"

    monkeypatch.setattr(pdf_review, "download_pdf", lambda *args, **kwargs: Downloaded())
    monkeypatch.setattr(pdf_review, "_native_text", lambda _doc: ("JBL JBLQ350WLBLKAM", 18))
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")

    result = pdf_review.inspect_pdf_candidate(identity, Downloaded.final_url, tmp_path / "cache")

    assert result.identity_accepted is True
    assert result.identity_pending_ocr is False
    assert result.ocr_recommended is True


def test_scanned_pdf_without_native_identity_is_pending_ocr_not_rejected(tmp_path, monkeypatch):
    from product_intelligence import pdf_review

    source = _write_pdf(tmp_path / "scan.pdf", " ")

    class Downloaded:
        path = source
        source_url = "https://example.test/JBLQ350WLBLKAM-manual.pdf"
        final_url = "https://example.test/JBLQ350WLBLKAM-manual.pdf"
        content_type = "application/pdf"
        size_bytes = source.stat().st_size
        sha256 = "ghi"

    monkeypatch.setattr(pdf_review, "download_pdf", lambda *args, **kwargs: Downloaded())
    monkeypatch.setattr(pdf_review, "_native_text", lambda _doc: ("", 0))
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")

    result = pdf_review.inspect_pdf_candidate(identity, Downloaded.final_url, tmp_path / "cache")

    assert result.identity_accepted is False
    assert result.identity_pending_ocr is True
    assert result.ocr_recommended is True
    assert result.identity_reason == "strong_identifier_without_brand_binding"


def test_real_identity_conflict_is_never_pending_ocr(tmp_path, monkeypatch):
    from product_intelligence import pdf_review

    source = _write_pdf(tmp_path / "wrong.pdf", "JBL Tune 520C product document")

    class Downloaded:
        path = source
        source_url = "https://example.test/tune-520c.pdf"
        final_url = "https://example.test/tune-520c.pdf"
        content_type = "application/pdf"
        size_bytes = source.stat().st_size
        sha256 = "jkl"

    monkeypatch.setattr(pdf_review, "download_pdf", lambda *args, **kwargs: Downloaded())
    identity = ProductIdentity(brand="JBL", model="Tune 530C")

    result = pdf_review.inspect_pdf_candidate(identity, Downloaded.final_url, tmp_path / "cache")

    assert result.identity_accepted is False
    assert result.identity_pending_ocr is False
    assert result.identity_reason == "sibling_model_url_conflict"


def test_review_candidate_score_prefers_exact_manual():
    from product_intelligence.pdf_review import score_review_candidate

    exact_manual = score_review_candidate(
        likely_official=True,
        document_type="manual",
        discovery_score=0.8,
        identity_accepted=True,
        identity_confidence=0.99,
        native_text_chars=5000,
    )
    weak_catalog = score_review_candidate(
        likely_official=False,
        document_type="technical_pdf",
        discovery_score=0.2,
        identity_accepted=False,
        identity_confidence=0.0,
        native_text_chars=100,
    )

    assert exact_manual > weak_catalog
    assert 0 <= weak_catalog <= 100
    assert 0 <= exact_manual <= 100
