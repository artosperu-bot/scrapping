from __future__ import annotations

import pytest

from product_intelligence.social_video_downloader import (
    VideoDownloadError,
    VideoSelectionRequired,
    download_social_video,
)
from product_intelligence.video_page_discovery import VideoCandidate


def test_unsupported_page_discovers_single_video_and_retries_same_downloader(monkeypatch, tmp_path):
    calls = {"urls": [], "discover": 0}

    class FakeYDL:
        def __init__(self, options):
            self.options = options
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def extract_info(self, url, download=True):
            calls["urls"].append(url)
            if url == "https://example.com/article":
                raise RuntimeError("Unsupported URL: generic webpage")
            target = tmp_path / "Embedded demo [embedded-1].mp4"
            target.write_bytes(b"verified-mp4")
            return {
                "id": "embedded-1",
                "title": "Embedded demo",
                "extractor_key": "Youtube",
                "webpage_url": url,
                "requested_downloads": [{"filepath": str(target)}],
            }
        def prepare_filename(self, _info):
            return str(tmp_path / "Embedded demo [embedded-1].mp4")

    def fake_discover(url, **_kwargs):
        calls["discover"] += 1
        assert url == "https://example.com/article"
        return [
            VideoCandidate(
                url="https://www.youtube.com/watch?v=YE7VzlLtp-4",
                provider="youtube",
                source_kind="iframe",
                title="Product demo",
                score=117.0,
            )
        ]

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr("product_intelligence.social_video_downloader.resolve_ffmpeg_exe", lambda: None)
    monkeypatch.setattr("product_intelligence.video_page_discovery.discover_video_candidates", fake_discover)

    result = download_social_video("https://example.com/article", tmp_path, quality="720p")

    assert result.local_path.read_bytes() == b"verified-mp4"
    assert result.provider == "Youtube"
    assert calls["discover"] == 1
    assert calls["urls"] == [
        "https://example.com/article",
        "https://www.youtube.com/watch?v=YE7VzlLtp-4",
    ]


def test_private_or_login_failure_never_scrapes_page_as_a_bypass(monkeypatch, tmp_path):
    calls = {"discover": 0}

    class FakeYDL:
        def __init__(self, options): self.options = options
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def extract_info(self, url, download=True):
            raise RuntimeError("Sign in required: private video")

    def forbidden_discover(*_args, **_kwargs):
        calls["discover"] += 1
        return []

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr("product_intelligence.social_video_downloader.resolve_ffmpeg_exe", lambda: None)
    monkeypatch.setattr("product_intelligence.video_page_discovery.discover_video_candidates", forbidden_discover)

    with pytest.raises(VideoDownloadError, match="LOGIN_OR_PRIVATE_REQUIRED"):
        download_social_video("https://example.com/private", tmp_path)
    assert calls["discover"] == 0


def test_two_near_equal_primary_candidates_require_user_selection(monkeypatch, tmp_path):
    class FakeYDL:
        def __init__(self, options): self.options = options
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def extract_info(self, url, download=True):
            raise RuntimeError("Unsupported URL: webpage with multiple players")

    candidates = [
        VideoCandidate(
            url="https://www.youtube.com/watch?v=AAAAAAAAAAA",
            provider="youtube",
            source_kind="iframe",
            title="Demo A",
            score=117.0,
        ),
        VideoCandidate(
            url="https://player.vimeo.com/video/123456",
            provider="vimeo",
            source_kind="iframe",
            title="Demo B",
            score=116.0,
        ),
    ]

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr("product_intelligence.social_video_downloader.resolve_ffmpeg_exe", lambda: None)
    monkeypatch.setattr(
        "product_intelligence.video_page_discovery.discover_video_candidates",
        lambda *_args, **_kwargs: candidates,
    )

    with pytest.raises(VideoSelectionRequired) as caught:
        download_social_video("https://example.com/multiple", tmp_path)

    assert caught.value.candidates == tuple(candidates)
    assert "2" in str(caught.value)


def test_no_discovered_video_preserves_original_unsupported_error(monkeypatch, tmp_path):
    class FakeYDL:
        def __init__(self, options): self.options = options
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def extract_info(self, url, download=True):
            raise RuntimeError("Unsupported URL: no playable media")

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr("product_intelligence.social_video_downloader.resolve_ffmpeg_exe", lambda: None)
    monkeypatch.setattr(
        "product_intelligence.video_page_discovery.discover_video_candidates",
        lambda *_args, **_kwargs: [],
    )

    with pytest.raises(VideoDownloadError, match="UNSUPPORTED_URL"):
        download_social_video("https://example.com/no-video", tmp_path)
