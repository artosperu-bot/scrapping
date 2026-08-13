from pathlib import Path
R=Path(__file__).parents[1]
def test_ui_shell_contract():
    assert 'modern_desktop' in (R/'run_desktop.py').read_text()
    s=(R/'src/product_intelligence/modern_desktop.py').read_text()
    assert 'class App(PriceApp)' in s and '_global_running' not in s
    w=(R/'src/product_intelligence/ui_widgets.py').read_text()
    assert 'class AnimatedStateGif' in w and 'class ProcessStatusCard' in w and 'class SessionLogNotebook' in w
    assert 'def configure_business_theme' in (R/'src/product_intelligence/ui_theme.py').read_text()

def test_modern_shell_delegates_instead_of_reimplementing_engines():
    s=(R/'src/product_intelligence/modern_desktop.py').read_text()
    assert 'def _build_media_tab' in s
    assert 'def _start_media_indices' in s and 'super()._start_media_indices' in s
    assert 'def _start_price_indices' in s and 'super()._start_price_indices' in s
    assert 'def start_process_session' in s
    assert 'run_media_product(' not in s and 'run_price_product(' not in s and 'run_batch(' not in s
