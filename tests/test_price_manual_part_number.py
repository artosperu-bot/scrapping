from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_price_ui_can_add_manual_part_number_to_existing_search_flow():
    source = (ROOT / "src" / "product_intelligence" / "price_desktop.py").read_text(encoding="utf-8")

    # The manual input belongs only to the Price UI. It must create the same
    # ProductIdentity shape that the already-working price workflow consumes.
    assert 'text="Part Number / MPN"' in source
    assert "_add_manual_price_product" in source
    assert "ProductIdentity(mpn=part_number)" in source
    assert "_price_identity_for_list_index" in source

    # The existing price engine remains the terminal execution path.
    assert "run_price_product(identity, output_root, on_event=on_event, max_sources=48)" in source


def test_final_organized_price_ui_keeps_manual_part_number_controls():
    source = (ROOT / "src" / "product_intelligence" / "organized_desktop.py").read_text(encoding="utf-8")

    # organized_desktop rebuilds the visible Price workspace after the base UI.
    # The final packaged screen must therefore recreate the manual MPN controls.
    assert 'text="Part Number / MPN"' in source
    assert "textvariable=self.price_manual_part_number" in source
    assert 'text="Agregar"' in source
    assert "command=self._add_manual_price_product" in source
    assert "Analiza un Excel o agrega un Part Number para buscar precios." in source
