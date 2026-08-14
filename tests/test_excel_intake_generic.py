from __future__ import annotations

from openpyxl import Workbook

from product_intelligence.batch import detect_items


def _save_workbook(tmp_path, rows, title="Productos"):
    wb = Workbook()
    ws = wb.active
    ws.title = title
    for r, values in enumerate(rows, 1):
        for c, value in enumerate(values, 1):
            ws.cell(r, c).value = value
    path = tmp_path / "products.xlsx"
    wb.save(path)
    return path


def test_one_column_part_number_sheet_is_a_valid_product_table(tmp_path):
    path = _save_workbook(
        tmp_path,
        [
            ["Part Number"],
            ["TE-2128S"],
            ["IPC-S042"],
            ["JBLQ350WLBLKAM"],
        ],
    )

    items = detect_items(str(path))

    assert [(item.row, item.identity.mpn) for item in items] == [
        (2, "TE-2128S"),
        (3, "IPC-S042"),
        (4, "JBLQ350WLBLKAM"),
    ]
