from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_price_desktop_adds_tab_8_and_independent_controls():
    source = (ROOT / "src" / "product_intelligence" / "price_desktop.py").read_text(encoding="utf-8")
    assert 'text="8. Precios y competencia"' in source
    assert "BUSCAR PRECIOS" in source
    assert "Procesar todos los productos" in source
    assert "ttk.Treeview" in source
    assert "run_price_product" in source
    assert "run_batch" not in source
    assert "run_media_product" not in source
    assert "queue.Queue" in source
    assert "after(" in source


def test_exe_entrypoint_uses_price_desktop_extension():
    source = (ROOT / "run_desktop.py").read_text(encoding="utf-8")
    assert "from product_intelligence.price_desktop import main" in source
