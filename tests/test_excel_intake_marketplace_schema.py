from openpyxl import Workbook

from product_intelligence.excel_intake import analyze_workbook_intake


def _build_marketplace_template(path):
    wb = Workbook()
    data = wb.active
    data.title = "Data"
    data.append(["Categoría", "sku_seller", "Nombre", "Descripcion", "Marca", "Imagen principal"])
    data.append(["categoria", "sku_seller", "nombre", "descripcion", "marca", "imagen"])
    rows = [
        ("ST6290132581599", "SEISA IPC-S042 CÁMARA DE SEGURIDAD", "IPC-S042", "6290132581599"),
        ("ST6290132588048", "SEISA IPC-SY9 CÁMARA DE SEGURIDAD", "IPC-SY9-BK", "6290132588048"),
        ("ST6290132576144", "SEISA IPC-ZAS02 CÁMARA DE SEGURIDAD", "IPC-ZAS02", "6290132576144"),
    ]
    for sku, name, pn, gtin in rows:
        description = f"Ficha técnica\nMODELO: {pn}\nPARTNUMBER: {pn}\nEAN/UPC: {gtin}"
        data.append(["CAMARAS DE SEGURIDAD", sku, name, description, "SEISA", f"https://example.invalid/{pn}.jpg"])

    columns = wb.create_sheet("Columns")
    columns.append(["Código", "Etiqueta", "Descripción", "Valor de ejemplo", "CAMARAS DE SEGURIDAD"])
    for code, label in [
        ("categoria", "Categoría"),
        ("sku_seller", "sku_seller"),
        ("nombre", "Nombre"),
        ("ShortDescription", "Descripción Corta"),
        ("descripcion", "Descripcion"),
        ("marca", "Marca"),
        ("imagen", "Imagen principal"),
        ("thumbnail", "imagen miniatura"),
        ("imagen2", "imagen2"),
    ]:
        columns.append([code, label, "", None, "REQUIRED"])

    wb.save(path)


def test_metadata_schema_sheet_does_not_become_fake_products(tmp_path):
    path = tmp_path / "marketplace.xlsx"
    _build_marketplace_template(path)

    result = analyze_workbook_intake(str(path))

    assert len(result.products) == 3
    assert [p.row for p in result.products] == [3, 4, 5]
    assert all(p.sheet == "Data" for p in result.products)


def test_explicit_partnumber_in_product_content_is_preferred_and_gtin_is_preserved(tmp_path):
    path = tmp_path / "marketplace.xlsx"
    _build_marketplace_template(path)

    result = analyze_workbook_intake(str(path))

    assert [p.identity.mpn for p in result.products] == ["IPC-S042", "IPC-SY9-BK", "IPC-ZAS02"]
    assert [p.identity.gtin for p in result.products] == ["6290132581599", "6290132588048", "6290132576144"]
    assert all(p.audit["identity_type"] == "PART_NUMBER_FROM_CONTENT" for p in result.products)
