from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path


def test_run_desktop_routes_pdf_e2e_smoke_before_gui_bootstrap():
    source = Path("run_desktop.py").read_text(encoding="utf-8")
    assert "--pdf-e2e-smoke" in source
    assert "product_intelligence.pdf_packaged_smoke" in source
    assert "managed_main()" not in source.split("if __name__ == \"__main__\":", 1)[0].splitlines()[-1:]


def test_packaged_smoke_validates_physical_pdf_paths_and_report_schema(tmp_path):
    spec = importlib.util.find_spec("product_intelligence.pdf_packaged_smoke")
    assert spec is not None, "Packaged EXE needs a dedicated PDF runtime smoke module"
    module = importlib.import_module("product_intelligence.pdf_packaged_smoke")

    good = tmp_path / "pdf_evidence" / "PART-1" / "manual.pdf"
    good.parent.mkdir(parents=True)
    good.write_bytes(b"%PDF-1.4\n% packaged smoke fixture\n")
    missing = good.with_name("missing.pdf")
    wrong_suffix = good.with_suffix(".txt")
    wrong_suffix.write_text("not pdf", encoding="utf-8")

    assert module.validate_physical_pdf_paths([str(good)]) == [str(good.resolve())]

    for invalid in ([str(missing)], [str(wrong_suffix)]):
        try:
            module.validate_physical_pdf_paths(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected physical PDF validation failure for {invalid}")

    report = module.build_smoke_report(
        output_dir=tmp_path,
        products=[
            {
                "part_number": "PART-1",
                "status": "PASS",
                "query_count": 4,
                "validated_count": 1,
                "physical_pdf_paths": [str(good.resolve())],
            }
        ],
    )
    assert report["status"] == "PASS"
    assert report["products"][0]["query_count"] == 4
    assert report["products"][0]["validated_count"] == 1
    assert report["products"][0]["physical_pdf_paths"] == [str(good.resolve())]

    report_path = tmp_path / "pdf-packaged-smoke.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded["status"] == "PASS"
