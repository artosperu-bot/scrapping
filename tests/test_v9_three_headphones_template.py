from pathlib import Path

from openpyxl import load_workbook

from product_intelligence.excel_mapper_v8 import fill_excel_v8
from product_intelligence.models import ProductRecord


PART_NUMBERS = [
    "JBLQ350WLBLKAM",
    "JBLENDURRUN3BTBAM",
    "JBLT530CBLKAM",
]


def _record(root: Path, part_number: str) -> ProductRecord:
    return ProductRecord.model_validate_json(
        (root / "demo_output" / f"{part_number}.v7.json").read_text(encoding="utf-8")
    )


def test_three_headphones_fill_consecutive_template_rows(tmp_path):
    root = Path(__file__).resolve().parents[1]
    template = root / "examples" / "ProductCreationTemplate_reference.xlsx"
    records = [_record(root, pn) for pn in PART_NUMBERS]
    assignments = {
        ("Subir plantilla", 5 + index): record
        for index, record in enumerate(records)
    }

    output = tmp_path / "headphones_completed.xlsx"
    trace = tmp_path / "trace.json"
    report = fill_excel_v8(
        str(template),
        str(output),
        records,
        overwrite=True,
        trace_path=str(trace),
        row_assignments=assignments,
    )

    assert output.exists()
    assert trace.exists()
    assert report["summary"]["written_count"] > 0

    wb = load_workbook(output, data_only=False)
    ws = wb["Subir plantilla"]

    # Rows must stay independent. The first two demo records are valid and must land on
    # their own rows. The historical Tune 530C demo record is intentionally CONFLICT
    # (manufacturer SKU differs), so the safe behavior is to leave it blank rather than
    # copy another product into row 7.
    names = [str(ws[f"A{row}"].value or "") for row in (5, 6, 7)]
    assert "Quantum 350" in names[0]
    assert "Endurance Run 3" in names[1]
    assert "Quantum 350" not in names[2]
    assert "Endurance Run 3" not in names[2]
    if names[2]:
        assert "Tune 530C" in names[2]

    # Template-only seller price examples must not survive the recalculation.
    assert ws["M5"].value != "999.999,99"
    assert ws["N5"].value != "999.999,99"

    # Obvious instruction examples/placeholders must not survive as product facts.
    assert ws["D5"].value != "Esto es un párrafo"
    assert ws["AC5"].value != "Ej. 80 cm x 45 cm x 63 cm // E.g. 80 cm x 45 cm x 63 cm"
    assert ws["AD5"].value != "10 m/s"
