from pathlib import Path


ROOT = Path(__file__).parents[1]
MEDIA = ROOT / "src" / "product_intelligence" / "media_desktop.py"


def test_multimedia_tab_exposes_social_video_downloader_controls():
    source = MEDIA.read_text(encoding="utf-8")
    assert "Descargar video por URL" in source
    assert "Descargar MP4" in source
    assert "Mejor calidad" in source
    assert "1080p" in source
    assert "720p" in source
    assert "480p" in source
    assert "social_video_url" in source
    assert "social_video_quality" in source
    assert "_start_social_video_download" in source


def test_social_download_uses_worker_thread_and_existing_gallery_card():
    source = MEDIA.read_text(encoding="utf-8")
    body = source.split("def _start_social_video_download", 1)[1]
    assert "threading.Thread" in body
    assert "download_social_video" in body
    assert '"type": "social_video_done"' in body
    assert "_add_media_card" in source
    assert '"media_type": "video"' in source


def test_social_download_state_is_separate_from_media_discovery_state():
    source = MEDIA.read_text(encoding="utf-8")
    assert "_social_video_running" in source
    assert "_media_running" in source
    social_body = source.split("def _start_social_video_download", 1)[1].split("\n    def ", 1)[0]
    assert "self._media_running =" not in social_body
