from pathlib import Path


def test_price_ui_organization_keeps_price_engine_isolated():
    source = Path('src/product_intelligence/organized_desktop.py').read_text(encoding='utf-8')
    engine = Path('src/product_intelligence/price_workflow.py').read_text(encoding='utf-8')
    for tab in ('Buscar', 'Ofertas', 'Cobertura', 'Auditoría'):
        assert f'text="{tab}"' in source
    assert 'def run_price_product(' in engine
    assert 'run_price_product(' not in source
