from pathlib import Path

SRC = Path(__file__).parents[1] / "src" / "product_intelligence"


def test_desktop_uses_full_price_source_budget():
    source = (SRC / "price_desktop.py").read_text(encoding="utf-8")
    assert "max_sources=12" not in source
    assert "max_sources=48" in source


def test_workflow_keeps_all_valid_offers_after_quality_gates():
    source = (SRC / "price_workflow.py").read_text(encoding="utf-8")
    assert "valid, rejected_outliers = filter_market_outliers(trusted)" in source
    assert "for row in valid:" in source
    assert "emit(\"offer\", offer=row.to_dict())" in source
    assert "return valid" in source


def test_identity_priority_remains_part_number_first():
    source = (SRC / "price_workflow.py").read_text(encoding="utf-8")
    assert "identity.mpn or identity.ean or identity.upc or identity.gtin" in source
