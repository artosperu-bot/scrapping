from pathlib import Path


SRC = Path(__file__).parents[1] / "src" / "product_intelligence" / "price_desktop.py"


def _source() -> str:
    return SRC.read_text(encoding="utf-8")


def test_price_module_has_internal_offer_coverage_and_audit_tabs():
    source = _source()
    assert 'text="Ofertas"' in source
    assert 'text="Cobertura"' in source
    assert 'text="Auditoría"' in source
    assert "price_results_notebook" in source


def test_price_module_renders_full_coverage_including_no_hay():
    source = _source()
    assert "def _render_price_coverage" in source
    assert "price_coverage_tree" in source
    assert 'row.get("status")' in source
    assert "NO_HAY" in source


def test_zero_offer_completion_is_explicit_not_blank():
    source = _source()
    assert "0 ofertas válidas" in source
    assert "Búsqueda completada" in source


def test_price_specific_audit_stays_inside_price_module():
    source = _source()
    assert "def _append_price_audit" in source
    assert "price_audit_tree" in source
    assert "Hora" in source
    assert "Fuente" in source
    assert "Estado" in source
    assert "Detalle" in source
