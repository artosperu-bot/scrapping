from pathlib import Path


def _desktop_source() -> str:
    return (Path(__file__).parents[1] / "src" / "product_intelligence" / "desktop.py").read_text(encoding="utf-8")


def test_desktop_has_standalone_media_tab_and_workflow_import():
    source = _desktop_source()
    assert "from .media_workflow import run_media_product" in source
    assert 'text="7. Fotos y videos"' in source
    assert "BUSCAR Y DESCARGAR MULTIMEDIA" in source
    assert "Procesar todos los productos" in source


def test_media_execution_is_separate_from_run_batch():
    source = _desktop_source()
    start = source.index("def _start_media_indices")
    end = source.index("def ", start + 5)
    media_method = source[start:end]
    assert "run_media_product" in media_method
    assert "run_batch" not in media_method


def test_media_tab_supports_live_gallery_and_manual_urls():
    source = _desktop_source()
    assert "self.media_manual_urls" in source
    assert "self.media_events" in source
    assert "_drain_media_events" in source
    assert "_add_media_card" in source
    assert "ImageTk.PhotoImage" in source
