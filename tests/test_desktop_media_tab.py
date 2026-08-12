from pathlib import Path


ROOT = Path(__file__).parents[1]


def _media_desktop_source() -> str:
    return (ROOT / "src" / "product_intelligence" / "media_desktop.py").read_text(encoding="utf-8")


def test_exe_entrypoint_preserves_media_desktop_extension_chain():
    source = (ROOT / "run_desktop.py").read_text(encoding="utf-8")
    assert "from product_intelligence.price_desktop import main" in source
    price_source = (ROOT / "src" / "product_intelligence" / "price_desktop.py").read_text(encoding="utf-8")
    assert "from .media_progress_desktop import App as MediaProgressApp" in price_source
    progress_source = (ROOT / "src" / "product_intelligence" / "media_progress_desktop.py").read_text(encoding="utf-8")
    assert "from .media_desktop import App as MediaApp" in progress_source


def test_desktop_has_standalone_media_tab_and_workflow_import():
    source = _media_desktop_source()
    assert "from .media_workflow import run_media_product" in source
    assert 'text="7. Fotos y videos"' in source
    assert "BUSCAR Y DESCARGAR MULTIMEDIA" in source
    assert "Procesar todos los productos" in source


def test_media_execution_is_separate_from_run_batch():
    source = _media_desktop_source()
    start = source.index("    def _start_media_indices")
    end = source.index("\n    def _drain_media_events", start)
    media_method = source[start:end]
    assert "run_media_product" in media_method
    assert "run_batch" not in media_method


def test_media_tab_supports_live_gallery_and_manual_urls():
    source = _media_desktop_source()
    assert "self.media_manual_urls" in source
    assert "self.media_events" in source
    assert "_drain_media_events" in source
    assert "_add_media_card" in source
    assert "ImageTk.PhotoImage" in source
