from __future__ import annotations

from pathlib import Path

import pytest

import product_intelligence.social_video_downloader as downloader
from product_intelligence.social_video_downloader import (
    VideoDownloadError,
    VideoDownloadResult,
    download_social_video,
)
from product_intelligence.video_page_discovery import VideoCandidate


ROOT = Path(__file__).parents[1]


def test_recoverable_generic_page_failure_still_discovers_embedded_video(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_download(source_url, destination, *, quality, on_progress):
        calls.append(source_url)
        if source_url == "https://example.com/product-page":
            raise VideoDownloadError("DOWNLOAD_FAILED: generic extractor could not resolve webpage")
        target = tmp_path / "embedded-youtube.mp4"
        target.write_bytes(b"video")
        return VideoDownloadResult(
            title="Embedded YouTube",
            provider="Youtube",
            source_url=source_url,
            local_path=target,
            quality=quality,
        )

    monkeypatch.setattr(downloader, "_download_with_yt_dlp", fake_download)
    monkeypatch.setattr(
        "product_intelligence.video_page_discovery.discover_video_candidates",
        lambda *_args, **_kwargs: [
            VideoCandidate(
                url="https://www.youtube.com/watch?v=YE7VzlLtp-4",
                provider="youtube",
                source_kind="iframe",
                title="Product demo",
                score=117.0,
            )
        ],
    )

    result = download_social_video("https://example.com/product-page", tmp_path)

    assert result.local_path.read_bytes() == b"video"
    assert calls == [
        "https://example.com/product-page",
        "https://www.youtube.com/watch?v=YE7VzlLtp-4",
    ]


def test_definitive_access_failure_is_not_bypassed_by_page_discovery(monkeypatch, tmp_path):
    calls = {"discover": 0}

    def fake_download(*_args, **_kwargs):
        raise VideoDownloadError("LOGIN_OR_PRIVATE_REQUIRED: Sign in required")

    def forbidden_discovery(*_args, **_kwargs):
        calls["discover"] += 1
        return []

    monkeypatch.setattr(downloader, "_download_with_yt_dlp", fake_download)
    monkeypatch.setattr(
        "product_intelligence.video_page_discovery.discover_video_candidates",
        forbidden_discovery,
    )

    with pytest.raises(VideoDownloadError, match="LOGIN_OR_PRIVATE_REQUIRED"):
        download_social_video("https://example.com/private-video", tmp_path)
    assert calls["discover"] == 0


def test_youtube_runtime_and_ejs_are_part_of_the_packaged_desktop_contract():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    spec = (ROOT / "ProductIntelligence.spec").read_text(encoding="utf-8")
    build = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release-windows.yml").read_text(encoding="utf-8")

    assert 'yt-dlp[default]>=2026.7.4' in project
    assert "collect_all('yt_dlp_ejs')" in spec
    assert "vendor/deno" in spec.replace("\\", "/")
    assert "denoland/setup-deno" in build
    assert "denoland/setup-deno" in release
    assert "deno.exe" in build
    assert "deno.exe" in release


def test_downloader_exposes_a_runtime_resolver_for_bundled_deno():
    assert callable(getattr(downloader, "resolve_js_runtime", None))
