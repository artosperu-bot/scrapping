from __future__ import annotations

from product_intelligence.video_page_discovery import (
    VideoCandidate,
    _extract_candidates_from_html,
    discover_video_candidates,
)


def test_static_html_discovers_primary_video_embed_hls_dash_and_dedupes():
    base = "https://shop.example.com/products/demo"
    html = """
    <html><head>
      <meta property="og:video" content="https://cdn.example.com/master.m3u8">
    </head><body>
      <video controls width="1280" height="720" src="/media/main.mp4">
        <source src="/media/main.mp4" type="video/mp4">
        <source src="https://cdn.example.com/stream.mpd" type="application/dash+xml">
      </video>
      <iframe title="Product demo" src="https://www.youtube.com/embed/YE7VzlLtp-4"></iframe>
      <video muted autoplay loop width="120" height="80" src="/assets/background.webm"></video>
    </body></html>
    """

    rows = _extract_candidates_from_html(base, html)
    urls = [row.url for row in rows]

    assert urls.count("https://shop.example.com/media/main.mp4") == 1
    assert "https://cdn.example.com/master.m3u8" in urls
    assert "https://cdn.example.com/stream.mpd" in urls
    assert "https://www.youtube.com/embed/YE7VzlLtp-4" in urls
    assert "https://shop.example.com/assets/background.webm" in urls

    youtube = next(row for row in rows if "youtube.com/embed" in row.url)
    background = next(row for row in rows if "background.webm" in row.url)
    assert youtube.provider == "youtube"
    assert youtube.source_kind == "iframe"
    assert youtube.score > background.score


def test_non_http_sources_are_rejected_and_relative_urls_are_normalized():
    rows = _extract_candidates_from_html(
        "https://example.com/catalog/item",
        """
        <video src="javascript:alert(1)"></video>
        <source src="data:video/mp4;base64,AAAA">
        <source src="../video/demo.mp4">
        """,
    )
    assert [row.url for row in rows] == ["https://example.com/video/demo.mp4"]


def test_static_strong_candidate_skips_browser_fallback(monkeypatch):
    calls = {"browser": 0}
    monkeypatch.setattr(
        "product_intelligence.video_page_discovery._fetch_static_html",
        lambda *_args, **_kwargs: '<meta property="og:video" content="https://cdn.example.com/main.mp4">',
    )

    def fake_browser(*_args, **_kwargs):
        calls["browser"] += 1
        return "", []

    monkeypatch.setattr(
        "product_intelligence.video_page_discovery._discover_browser_evidence",
        fake_browser,
    )

    rows = discover_video_candidates("https://example.com/article")
    assert rows[0].url == "https://cdn.example.com/main.mp4"
    assert calls["browser"] == 0


def test_dynamic_browser_fallback_discovers_rendered_embed_and_network_manifest(monkeypatch):
    monkeypatch.setattr(
        "product_intelligence.video_page_discovery._fetch_static_html",
        lambda *_args, **_kwargs: "<html><body><div id='player'></div></body></html>",
    )
    calls = {"browser": 0}

    def fake_browser(*_args, **_kwargs):
        calls["browser"] += 1
        return (
            '<iframe title="Demo" src="https://player.vimeo.com/video/123456"></iframe>',
            [
                ("https://cdn.example.com/live/master.m3u8", "application/vnd.apple.mpegurl"),
                ("https://analytics.example.com/pixel", "image/gif"),
            ],
        )

    monkeypatch.setattr(
        "product_intelligence.video_page_discovery._discover_browser_evidence",
        fake_browser,
    )

    rows = discover_video_candidates("https://example.com/dynamic")
    urls = {row.url for row in rows}
    assert calls["browser"] == 1
    assert "https://player.vimeo.com/video/123456" in urls
    assert "https://cdn.example.com/live/master.m3u8" in urls
    assert "https://analytics.example.com/pixel" not in urls


def test_candidates_are_ranked_and_limited_deterministically(monkeypatch):
    monkeypatch.setattr(
        "product_intelligence.video_page_discovery._fetch_static_html",
        lambda *_args, **_kwargs: "".join(
            f'<video controls src="https://cdn.example.com/v{i}.mp4"></video>' for i in range(12)
        ),
    )
    monkeypatch.setattr(
        "product_intelligence.video_page_discovery._discover_browser_evidence",
        lambda *_args, **_kwargs: ("", []),
    )
    rows = discover_video_candidates("https://example.com/many", limit=5)
    assert len(rows) == 5
    assert all(isinstance(row, VideoCandidate) for row in rows)
    assert [row.score for row in rows] == sorted((row.score for row in rows), reverse=True)
