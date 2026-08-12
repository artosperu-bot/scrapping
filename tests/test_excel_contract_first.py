from pathlib import Path

from openpyxl import Workbook

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


def test_excel_description_defines_bluetooth_contract(tmp_path):
    path = tmp_path / "bluetooth_contract.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Subir plantilla"
    ws.append(["Especificaciones", "Especificaciones", "Precio"])
    ws.append([
        "Selecciona si el producto cuenta con bluetooth. // Select whether the product has Bluetooth.\n\n- Syntax: One value from the list",
        "Ingresa el modelo del producto. // Enter the product model.\n\n- Syntax: Text",
        "Ingresa el precio del producto en falabella.com.",
    ])
    ws.append([" ", " ", " ( Optional ) "])
    ws.append(["CuentaConBluetooth #1568", "Modelo #32", "PriceFalabella #52"])
    ws.append([None, "ABC-123", None])
    opts = wb.create_sheet("Opciones")
    opts.append(["CuentaConBluetooth #1568", "Dummy"])
    opts.append(["Sí", "A"])
    opts.append(["No", "B"])
    wb.save(path)

    plan = analyze_template_contract(str(path))
    bluetooth = next(field for field in all_fields(plan) if "CuentaConBluetooth" in field["label"])
    assert bluetooth["scrape"] is True
    assert bluetooth["value_type"] == "controlled"
    assert "bluetooth" in str(bluetooth["semantic"]).lower()
    assert {str(x) for x in bluetooth["options"]} >= {"Sí", "No"}


def test_seller_sku_is_not_product_identity():
    items = detect_items(str(template_path()))
    assert items
    assert all(item.identity.sku is None for item in items)
