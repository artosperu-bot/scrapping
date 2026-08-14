from pathlib import Path

from PIL import Image


ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "product_intelligence"
ASSETS = SRC / "assets" / "progress"


def test_progress_animation_component_exists_and_is_ui_only():
    path = SRC / "progress_animation.py"
    assert path.is_file()
    source = path.read_text(encoding="utf-8")
    assert "class ProgressAnimation" in source
    assert "RUNNING" in source
    assert "COMPLETED" in source
    assert "ERROR" in source
    assert ".after(" in source
    assert "threading" not in source
    assert "scrap" not in source.lower()
    assert "mistral" not in source.lower()
    assert "ocr" not in source.lower()
    assert "price" not in source.lower()


def test_tom_and_jerry_gifs_are_real_animated_assets():
    processing = ASSETS / "processing.gif"
    completed = ASSETS / "completed.gif"
    assert processing.is_file()
    assert completed.is_file()
    for path in (processing, completed):
        with Image.open(path) as image:
            assert image.format == "GIF"
            assert getattr(image, "n_frames", 1) > 1
            assert image.width <= 600
            assert image.height <= 500


def test_progress_animation_is_shared_by_excel_media_and_price_shells():
    media = (SRC / "media_progress_desktop.py").read_text(encoding="utf-8")
    excel = (SRC / "pdf_desktop.py").read_text(encoding="utf-8")
    price = (SRC / "price_desktop.py").read_text(encoding="utf-8")
    assert "ProgressAnimation" in media
    assert "ProgressAnimation" in excel
    assert "ProgressAnimation" in price


def test_price_progress_layout_reserves_visible_animation_space_and_keeps_logic():
    source = (SRC / "price_desktop.py").read_text(encoding="utf-8")
    assert 'text="Progreso del proceso"' in source
    assert "height=190" in source
    assert "pack_propagate(False)" in source
    assert "ProgressAnimation(progress_visual, width=220, height=140)" in source
    assert "run_price_product(identity, output_root, on_event=on_event, max_sources=12)" in source
    assert 'self.price_tree.pack(side="left", fill="both", expand=True)' in source
    assert 'self.price_tree.bind("<Double-1>", self._open_price_offer)' in source


def test_media_progress_layout_reserves_visible_animation_space_and_keeps_gallery():
    source = (SRC / "media_progress_desktop.py").read_text(encoding="utf-8")
    assert 'text="Progreso del proceso"' in source
    assert "height=190" in source
    assert "pack_propagate(False)" in source
    assert "ProgressAnimation(right, width=220, height=140)" in source
    assert 'self.media_gallery_box.pack(fill="both", expand=True)' in source
    assert "return super()._start_media_indices(indices)" in source


def test_excel_progress_layout_reserves_visible_animation_space_and_keeps_batch_flow():
    source = (SRC / "pdf_desktop.py").read_text(encoding="utf-8")
    assert 'text="Progreso del proceso"' in source
    assert "height=190" in source
    assert "pack_propagate(False)" in source
    assert "ProgressAnimation(progress_visual, width=220, height=140)" in source
    assert "_excel_progress_log" in source
    assert r"^\[(\d+)/(\d+)\]" in source
    assert "position - 1" in source
    assert "result = run_batch(" in source


def test_running_price_and_media_progress_do_not_use_fake_stage_percentages():
    media = (SRC / "media_progress_desktop.py").read_text(encoding="utf-8")
    price = (SRC / "price_desktop.py").read_text(encoding="utf-8")
    assert "self._progress.product_percent" not in media
    assert "self._progress.overall_percent" not in media
    assert '"searching": 20' not in price
    assert '"validating": 55' not in price
    assert '"saving": 90' not in price
    assert 'mode="indeterminate"' in media
    assert 'mode="indeterminate"' in price


def test_excel_percent_comes_from_real_product_counter():
    source = (SRC / "pdf_desktop.py").read_text(encoding="utf-8")
    assert "_excel_progress_log" in source
    assert r"^\[(\d+)/(\d+)\]" in source
    assert "position - 1" in source


def test_error_state_does_not_switch_to_completed_asset():
    path = SRC / "progress_animation.py"
    source = path.read_text(encoding="utf-8")
    assert "completed.gif" in source
    assert "processing.gif" in source
    error_body = source.split("def set_error", 1)[1].split("\n    def ", 1)[0]
    assert "completed.gif" not in error_body


def test_pyinstaller_contract_explicitly_keeps_progress_assets():
    spec = (ROOT / "ProductIntelligence.spec").read_text(encoding="utf-8")
    assert "assets/progress" in spec.replace("\\", "/")
    assert "processing.gif" in spec
    assert "completed.gif" in spec


def test_release_version_is_0108_everywhere():
    version_source = (SRC / "version.py").read_text(encoding="utf-8")
    project_source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'APP_VERSION = "0.10.8"' in version_source
    assert 'version = "0.10.8"' in project_source


def test_progress_animation_broken_gif_never_escapes_into_business_workflow():
    source = (SRC / "progress_animation.py").read_text(encoding="utf-8")
    assert "_show_fallback" in source
    assert "except (OSError, EOFError, ValueError)" in source
    use_asset = source.split("def _use_asset", 1)[1].split("\n    def ", 1)[0]
    assert "try:" in use_asset
    assert "_show_fallback" in use_asset
    assert "except" in use_asset
