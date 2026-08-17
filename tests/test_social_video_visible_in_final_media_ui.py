from pathlib import Path


def test_final_media_ui_restores_social_video_downloader_after_organized_rebuild():
    visibility = Path("src/product_intelligence/social_video_visibility.py")
    assert visibility.exists(), "El shell final necesita una capa que restaure el downloader tras organized_desktop"

    source = visibility.read_text(encoding="utf-8")
    final_shell = Path("src/product_intelligence/final_live_ui_desktop.py").read_text(encoding="utf-8")

    assert 'text="Descargar video por URL"' in source
    assert "self.social_video_url" in source
    assert "self.social_video_quality" in source
    assert 'text="Descargar MP4"' in source
    assert "command=self._start_social_video_download" in source
    assert "página web" in source
    assert "video" in source and "embeb" in source
    assert "SocialVideoVisibilityMixin" in final_shell


def test_final_packaged_shell_still_inherits_real_social_downloader():
    media = Path("src/product_intelligence/media_desktop.py").read_text(encoding="utf-8")
    downloader = Path("src/product_intelligence/social_video_downloader.py").read_text(encoding="utf-8")

    assert "from .social_video_downloader import" in media
    assert "download_social_video" in media
    assert "VideoSelectionRequired" in media
    assert "result = download_social_video(" in media
    assert '"Mejor calidad", "1080p", "720p", "480p"' in media
    assert '"noplaylist": True' in downloader
    assert '"merge_output_format": "mp4"' in downloader


def test_pyinstaller_bundle_keeps_dynamic_page_discovery_and_ffmpeg_binary_gate():
    spec = Path("ProductIntelligence.spec").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/build-windows.yml").read_text(encoding="utf-8")
    assert "product_intelligence.video_page_discovery" in spec
    assert "collect_all('imageio_ffmpeg')" in spec
    assert "ffmpeg" in workflow.lower()
    assert "Bundled FFmpeg binary missing" in workflow
