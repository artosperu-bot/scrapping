from pathlib import Path

from product_intelligence.batch import detect_items
from product_intelligence.template_contract import analyze_template_contract


def template_path():
    return Path(__file__).resolve().parents[1] / "examples" / "ProductCreationTemplate_reference.xlsx"


def all_fields(plan):
    return [field for sheet in plan["sheets"] for field in sheet["fields"]]


def test_excel_contract_separates_product_media_and_seller_fields():
    plan = analyze_template_contract(str(template_path()))
    summary = plan["summary"]
    assert summary["fields_total"] >= 40
    assert summary["scrape_targets"] >= 15
    assert summary["media_slots"] >= 1
    assert summary["seller_inputs"] >= 1

    fields = all_fields(plan)
    price = next(field for field in fields if "PriceFalabella" in field["label"])
    image = next(field for field in fields if "Imagen principal" in field["label"])
    assert price["role"] == "SELLER_INPUT"
    assert price["scrape"] is False
    assert image["role"] == "MEDIA_TARGET"
    assert image["scrape"] is True


def test_excel_description_defines_bluetooth_contract():
    plan = analyze_template_contract(str(template_path()))
    bluetooth = next(field for field in all_fields(plan) if "CuentaConBluetooth" in field["label"])
    assert bluetooth["scrape"] is True
    assert bluetooth["value_type"] == "controlled"
    assert "bluetooth" in str(bluetooth["semantic"]).lower()


def test_seller_sku_is_not_product_identity():
    items = detect_items(str(template_path()))
    assert items
    assert all(item.identity.sku is None for item in items)
