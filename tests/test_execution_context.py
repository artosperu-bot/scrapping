from product_intelligence.execution_context import ExecutionSnapshot, ProductSnapshot, new_run_id


def test_run_ids_are_typed():
    assert new_run_id("excel").startswith("EXCEL-")
    assert new_run_id("media").startswith("MEDIA-")
    assert new_run_id("price").startswith("PRICE-")


def test_snapshot_copies_product_collection_and_urls():
    urls = ["https://example.test/a"]
    products = [ProductSnapshot(index=0, label="GENERIC-001", identity={"mpn": "GENERIC-001"}, manual_urls=tuple(urls))]
    snap = ExecutionSnapshot.create("EXCEL", "out", products, workbook="input.xlsx", overwrite=True)
    urls.append("https://example.test/b")
    products.clear()
    assert len(snap.products) == 1
    assert snap.products[0].manual_urls == ("https://example.test/a",)
    assert snap.workbook == "input.xlsx"
    assert snap.overwrite is True
