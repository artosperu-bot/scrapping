from pathlib import Path


def test_organized_media_ui_keeps_social_video_downloader_visible():
    source = Path("src/product_intelligence/organized_desktop.py").read_text(encoding="utf-8")

    assert 'text="Descargar video por URL"' in source
    assert "self.social_video_url" in source
    assert "self.social_video_quality" in source
    assert 'text="Descargar MP4"' in source
    assert "command=self._start_social_video_download" in source


def test_final_packaged_shell_still_inherits_real_social_downloader():
    media = Path("src/product_intelligence/media_desktop.py").read_text(encoding="utf-8")
    downloader = Path("src/product_intelligence/social_video_downloader.py").read_text(encoding="utf-8")

    assert "from .social_video_downloader import download_social_video" in media
    assert "result = download_social_video(" in media
    assert '"Mejor calidad", "1080p", "720p", "480p"' in media
    assert '"noplaylist": True' in downloader
    assert '"merge_output_format": "mp4"' in downloader
