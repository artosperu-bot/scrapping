from pathlib import Path

from PIL import Image


def test_media_progress_uses_shared_gif_animation_component():
    root = Path(__file__).parents[1]
    source = (root / "src" / "product_intelligence" / "media_progress_desktop.py").read_text(encoding="utf-8")
    animation = (root / "src" / "product_intelligence" / "progress_animation.py").read_text(encoding="utf-8")
    assert "ProgressAnimation" in source
    assert "processing.gif" in animation
    assert "completed.gif" in animation
    assert "ImageSequence" in animation
    assert "_draw_wolf" not in source


def test_tom_and_jerry_gifs_are_packaged_source_assets():
    root = Path(__file__).parents[1]
    assets = root / "src" / "product_intelligence" / "assets" / "progress"
    for name in ("processing.gif", "completed.gif"):
        gif = assets / name
        assert gif.exists()
        assert gif.stat().st_size > 100
        with Image.open(gif) as image:
            assert image.format == "GIF"
            assert getattr(image, "n_frames", 1) > 1
