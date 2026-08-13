from pathlib import Path

from product_intelligence.preflight import analyze_workbook


def test_preflight_exposes_products_and_excel_actions():
    root = Path(__file__).resolve().parents[1]
    template = root / "examples" / "ProductCreationTemplate_reference.xlsx"
    data = analyze_workbook(str(template))
    assert data["summary"]["products_detected"] == len(data["products"])
    assert all(p["identifier"] for p in data["products"])
    attributes = data["attributes"]
    assert attributes
    assert len(attributes) == data["summary"]["fields_total"]
    assert any(a["action"] == "INVESTIGAR" for a in attributes)
    assert any(a["action"] == "IMAGEN" for a in attributes)
    assert any(a["action"] == "DEJAR VACÍO / PROTEGER" for a in attributes)


def test_seller_fields_are_visible_but_never_research_targets():
    root = Path(__file__).resolve().parents[1]
    template = root / "examples" / "ProductCreationTemplate_reference.xlsx"
    data = analyze_workbook(str(template))
    by_label = {str(a["label"]): a for a in data["attributes"]}
    for label in ["SKU del vendedor #29", "QuantityFalabella #25", "PriceFalabella #52", "SalePriceFalabella #18"]:
        assert label in by_label
        assert by_label[label]["action"] == "DEJAR VACÍO / PROTEGER"


def test_reference_sheets_do_not_become_execution_attributes():
    root = Path(__file__).resolve().parents[1]
    template = root / "examples" / "ProductCreationTemplate_reference.xlsx"
    data = analyze_workbook(str(template))
    execution_sheets = {a["sheet"] for a in data["attributes"]}
    assert "Subir plantilla" in execution_sheets
    for reference in data["reference_sheets"]:
        assert reference not in execution_sheets
