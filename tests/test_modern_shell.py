from pathlib import Path
R=Path(__file__).parents[1]
def test_ui_shell_contract():
    assert 'modern_desktop' in (R/'run_desktop.py').read_text()
    s=(R/'src/product_intelligence/modern_desktop.py').read_text()
    assert 'class App(PriceApp)' in s
    assert '_global_running' not in s
    w=(R/'src/product_intelligence/ui_widgets.py').read_text()
    assert 'class ProcessStatusCard' in w
    assert 'class SessionLogNotebook' in w
