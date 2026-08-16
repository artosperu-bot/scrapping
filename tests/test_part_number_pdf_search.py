from types import SimpleNamespace

from product_intelligence.models import ProductIdentity
from product_intelligence.part_number_pdf_search import (
    MAX_REVIEW_PDF_PAGES,
    search_product_pdfs_by_part_number,
)


def _validated(url: str, pages: int):
    return SimpleNamespace(
        candidate=SimpleNamespace(url=url),
        inspection=SimpleNamespace(page_count=pages),
    )


def test_part_number_service_builds_code_only_identity_and_surfaces_only_short_validated_pdfs(monkeypatch, tmp_path):
    captured = {}
    rows = (
        _validated("https://manufacturer.example/spec.pdf", 2),
        _validated("https://manufacturer.example/manual.pdf", 10),
        _validated("https://manufacturer.example/long-manual.pdf", 11),
    )
    resolved_identity = ProductIdentity(
        brand="Example Brand",
        model="Nova X100",
        product_name="Example Brand Nova X100",
        mpn="PN-X100-BLK",
    )

    def fake_discover(identity, cache_dir, **kwargs):
        captured["identity"] = identity
        captured["cache_dir"] = cache_dir
        return SimpleNamespace(
            resolved=SimpleNamespace(identity=resolved_identity),
            candidates=rows,
            discovered_count=5,
            downloaded_count=3,
            rejected_count=2,
            duplicate_count=1,
        )

    monkeypatch.setattr(
        "product_intelligence.part_number_pdf_search.discover_validated_review_pdfs",
        fake_discover,
    )

    result = search_product_pdfs_by_part_number("PN-X100-BLK", tmp_path)

    assert captured["identity"].mpn == "PN-X100-BLK"
    assert captured["identity"].model == "PN-X100-BLK"
    assert [row.candidate.url for row in result.candidates] == [
        "https://manufacturer.example/spec.pdf",
        "https://manufacturer.example/manual.pdf",
    ]
    assert result.validated_count == 2
    assert result.page_limit_rejected_count == 1
    assert result.rejected_count == 3
    assert MAX_REVIEW_PDF_PAGES == 10


def test_part_number_service_rejects_empty_part_number(tmp_path):
    try:
        search_product_pdfs_by_part_number("   ", tmp_path)
    except ValueError as exc:
        assert str(exc) == "part_number_required"
    else:
        raise AssertionError("empty Part Number must fail closed")
