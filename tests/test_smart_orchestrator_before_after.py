from product_intelligence.smart_orchestrator_benchmark import BASELINE_REF, run_benchmark


def test_before_after_benchmark_is_grounded_in_release_windows_and_improves_control_flow(tmp_path):
    output = tmp_path / "smart-before-after.json"
    report = run_benchmark(output)

    assert BASELINE_REF == "73618a25263d8c45eec99519f7ac458f7783c785"
    assert report["baseline_ref"] == BASELINE_REF
    assert report["method"] == "DETERMINISTIC_STRUCTURAL_CONTROL_FLOW"
    assert output.is_file()

    before = report["summary"]["before"]
    after = report["summary"]["after"]
    assert after["verified_fields"] >= before["verified_fields"]
    assert after["product_failures"] < before["product_failures"]
    assert after["broad_web_calls"] < before["broad_web_calls"]
    assert after["known_false_positive_writes"] == 0
    assert before["known_false_positive_writes"] == 0

    pdf_zero = next(row for row in report["scenarios"] if row["scenario"] == "PDF_ZERO_TARGETED_WEB")
    assert pdf_zero["before"]["verified_fields"] == 0
    assert pdf_zero["before"]["product_failed"] is True
    assert pdf_zero["after"]["verified_fields"] == 1
    assert pdf_zero["after"]["product_failed"] is False
    assert pdf_zero["after"]["targeted_web_calls"] == 1


def test_before_after_full_pdf_proves_no_redundant_web(tmp_path):
    report = run_benchmark(tmp_path / "report.json")
    row = next(row for row in report["scenarios"] if row["scenario"] == "PDF_FULL")

    assert row["before"]["verified_fields"] == row["after"]["verified_fields"] == 2
    assert row["before"]["broad_web_calls"] >= 1
    assert row["after"]["broad_web_calls"] == 0
    assert row["after"]["targeted_web_calls"] == 0
    assert row["after"]["early_stop"] is True


def test_before_after_partial_pdf_targets_only_the_missing_field(tmp_path):
    report = run_benchmark(tmp_path / "report.json")
    row = next(row for row in report["scenarios"] if row["scenario"] == "PDF_PARTIAL")

    assert row["after"]["targeted_fields"] == [["driver_size"]]
    assert row["after"]["broad_web_calls"] == 0
    assert row["after"]["verified_fields"] == 2
