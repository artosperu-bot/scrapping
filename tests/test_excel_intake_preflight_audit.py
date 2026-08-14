from openpyxl import Workbook

from product_intelligence.preflight import analyze_workbook


def test_preflight_exposes_row_identity_and_search_query_without_web(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Carga"
    ws.append(["Part Number"])
    ws.append(["TE-2128S"])
    ws.append([None])
    path = tmp_path / "audit.xlsx"
    wb.save(path)

    data = analyze_workbook(str(path))

    assert data["products"][0]["identifier"] == "TE-2128S"
    assert data["products"][0]["search_requested"] is True
    assert data["products"][0]["search_query"] == '"TE-2128S"'

    sheet = data["intake_audit"]["sheets"][0]
    assert sheet["sheet_detected"] == "Carga"
    assert sheet["header_row_detected"] == 1
    assert sheet["normalized_headers"][1] == "part number"
    assert sheet["rows"][0]["row_accepted"] is True
    assert sheet["rows"][0]["identity_type"] == "PART_NUMBER"
