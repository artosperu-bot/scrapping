from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_desktop_profile_includes_downloader_ejs_and_ffmpeg_runtime():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    desktop = project.split('desktop = [', 1)[1].split(']', 1)[0]
    assert 'yt-dlp[default]>=2026.7.4' in desktop
    assert 'imageio-ffmpeg>=0.6.0' in desktop


def test_pyinstaller_collects_yt_dlp_ejs_deno_and_imageio_ffmpeg():
    spec = (ROOT / "ProductIntelligence.spec").read_text(encoding="utf-8")
    assert "collect_all('yt_dlp')" in spec
    assert "collect_all('yt_dlp_ejs')" in spec
    assert "collect_all('imageio_ffmpeg')" in spec
    assert "vendor'/'deno" in spec.replace('\\', '/')
    assert "product_intelligence.social_video_downloader" in spec
