from pathlib import Path

import pytest

from product_intelligence.social_video_downloader import (
    VideoDownloadError,
    build_format_selector,
    download_social_video,
    resolve_ffmpeg_exe,
)


def test_quality_selectors_prefer_mp4_and_enforce_height_ceiling():
    best = build_format_selector("best")
    q1080 = build_format_selector("1080p")
    q720 = build_format_selector("720p")
    assert "ext=mp4" in best
    assert "m4a" in best
    assert "height<=1080" in q1080
    assert "height<=720" in q720


def test_invalid_url_is_rejected_before_yt_dlp(tmp_path):
    with pytest.raises(VideoDownloadError, match="URL_INVALIDA"):
        download_social_video("file:///etc/passwd", tmp_path)


def test_resolve_ffmpeg_prefers_imageio_binary(monkeypatch, tmp_path):
    exe = tmp_path / "ffmpeg.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr("imageio_ffmpeg.get_ffmpeg_exe", lambda: str(exe))
    assert resolve_ffmpeg_exe() == str(exe)


def test_download_uses_yt_dlp_python_api_and_returns_verified_mp4(monkeypatch, tmp_path):
    calls = {}

    class FakeYDL:
        def __init__(self, options):
            calls["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, download=True):
            calls["url"] = url
            calls["download"] = download
            target = tmp_path / "Demo [abc123].mp4"
            target.write_bytes(b"mp4-data")
            for hook in calls["options"].get("progress_hooks", []):
                hook({"status": "finished", "filename": str(target), "info_dict": {"filepath": str(target)}})
            return {
                "id": "abc123",
                "title": "Demo",
                "extractor_key": "Youtube",
                "webpage_url": url,
                "duration": 5,
                "requested_downloads": [{"filepath": str(target)}],
            }

        def prepare_filename(self, _info):
            return str(tmp_path / "Demo [abc123].mp4")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr("product_intelligence.social_video_downloader.resolve_ffmpeg_exe", lambda: None)
    events = []
    result = download_social_video(
        "https://www.youtube.com/watch?v=abc123",
        tmp_path,
        quality="720p",
        on_progress=lambda event: events.append(event),
    )

    assert result.local_path.suffix.lower() == ".mp4"
    assert result.local_path.read_bytes() == b"mp4-data"
    assert result.provider == "Youtube"
    assert result.source_url.startswith("https://www.youtube.com/")
    assert calls["download"] is True
    assert "height<=720" in calls["options"]["format"]
    assert calls["options"]["merge_output_format"] == "mp4"
    assert calls["options"]["noplaylist"] is True
    assert events


def test_empty_or_non_mp4_output_is_not_success(monkeypatch, tmp_path):
    class FakeYDL:
        def __init__(self, options):
            self.options = options
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def extract_info(self, url, download=True):
            target = tmp_path / "bad.webm"
            target.write_bytes(b"x")
            return {"id": "bad", "title": "bad", "extractor_key": "Generic", "webpage_url": url, "requested_downloads": [{"filepath": str(target)}]}
        def prepare_filename(self, _info): return str(tmp_path / "bad.webm")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr("product_intelligence.social_video_downloader.resolve_ffmpeg_exe", lambda: None)
    with pytest.raises(VideoDownloadError, match="OUTPUT_MP4_NOT_FOUND"):
        download_social_video("https://example.com/video", tmp_path)


def test_packaged_nonstandard_ffmpeg_binary_is_passed_as_exact_executable(monkeypatch, tmp_path):
    calls = {}
    bundled = tmp_path / "ffmpeg-win64-v7.0.exe"
    bundled.write_bytes(b"fake-binary")

    class FakeYDL:
        def __init__(self, options):
            calls["options"] = options
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def extract_info(self, url, download=True):
            target = tmp_path / "Demo [ffmpeg-path].mp4"
            target.write_bytes(b"mp4-data")
            return {
                "id": "ffmpeg-path",
                "title": "Demo",
                "extractor_key": "Youtube",
                "webpage_url": url,
                "requested_downloads": [{"filepath": str(target)}],
            }
        def prepare_filename(self, _info):
            return str(tmp_path / "Demo [ffmpeg-path].mp4")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr(
        "product_intelligence.social_video_downloader.resolve_ffmpeg_exe",
        lambda: str(bundled),
    )

    download_social_video("https://www.youtube.com/watch?v=ffmpeg-path", tmp_path)

    assert calls["options"]["ffmpeg_location"] == str(bundled)
