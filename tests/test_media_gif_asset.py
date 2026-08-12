from pathlib import Path


def test_media_progress_uses_animated_gif_with_fallback():
    root = Path(__file__).parents[1]
    source = (root / "src" / "product_intelligence" / "media_progress_desktop.py").read_text(encoding="utf-8")
    assert "wolf_search.gif" in source
    assert "ImageSequence" in source
    assert "_draw_wolf" in source  # fallback remains available


def test_wolf_search_gif_is_packaged_source_asset():
    root = Path(__file__).parents[1]
    gif = root / "src" / "product_intelligence" / "assets" / "wolf_search.gif"
    assert gif.exists()
    assert gif.stat().st_size > 100
