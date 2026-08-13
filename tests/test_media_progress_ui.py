from pathlib import Path

from product_intelligence.media_progress import BatchProgress, stage_percent


ROOT = Path(__file__).parents[1]


def test_stage_percent_is_monotonic_and_done_is_100():
    stages = ["queued", "searching", "validating", "extracting", "downloading", "finalizing", "done"]
    values = [stage_percent(s) for s in stages]
    assert values == sorted(values)
    assert values[0] == 0
    assert values[-1] == 100


def test_batch_progress_combines_completed_and_current_product():
    progress = BatchProgress(total=4)
    progress.start_product(0, "PN-1")
    progress.set_stage("downloading")
    assert 0 < progress.overall_percent < 25
    progress.finish_product(downloaded=8, metadata_only=1)
    assert progress.completed == 1
    assert progress.overall_percent == 25
    progress.start_product(1, "PN-2")
    progress.set_stage("extracting")
    assert 25 < progress.overall_percent < 50


def test_batch_progress_reaches_100_only_when_all_products_finish():
    progress = BatchProgress(total=2)
    progress.start_product(0, "A")
    progress.finish_product(downloaded=2)
    assert progress.overall_percent == 50
    progress.start_product(1, "B")
    progress.finish_product(downloaded=3)
    assert progress.overall_percent == 100
    assert progress.completed == 2
    assert progress.downloaded == 5


def test_progress_desktop_contains_real_progress_bars_and_wolf_animation():
    source = (ROOT / "src" / "product_intelligence" / "media_progress_desktop.py").read_text(encoding="utf-8")
    assert "ttk.Progressbar" in source
    assert "self.media_overall_progress" in source
    assert "self.media_product_progress" in source
    assert "_animate_wolf" in source
    assert "_draw_wolf" in source
    assert "BatchProgress" in source
    assert 'text="Progreso del proceso"' in source


def test_progress_panel_is_packed_before_expandable_gallery_and_keeps_requested_height():
    source = (ROOT / "src" / "product_intelligence" / "media_progress_desktop.py").read_text(encoding="utf-8")
    # Regression: when the expandable gallery is packed first, Tk can squeeze the
    # later progress panel down to just its LabelFrame title (as seen in Windows).
    assert "self.media_gallery_box.pack_forget()" in source
    progress_pack = source.index('progress_box.pack(fill="x"')
    gallery_repack = source.index('self.media_gallery_box.pack(fill="both", expand=True)')
    assert progress_pack < gallery_repack
    assert 'height=150' in source or 'minsize=150' in source or 'propagate(False)' in source


def test_exe_preserves_progress_desktop_extension():
    source = (ROOT / "run_desktop.py").read_text(encoding="utf-8")
    assert "from product_intelligence.price_desktop import main" in source
    price_source = (ROOT / "src" / "product_intelligence" / "price_desktop.py").read_text(encoding="utf-8")
    assert "from .media_progress_desktop import App as MediaProgressApp" in price_source
