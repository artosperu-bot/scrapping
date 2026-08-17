from __future__ import annotations

from dataclasses import dataclass
import html as html_lib
import re
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


_MEDIA_EXTENSIONS = (".mp4", ".webm", ".mov", ".m4v", ".m3u8", ".mpd")
_MEDIA_CONTENT_TYPES = (
    "video/",
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "application/mpegurl",
    "application/dash+xml",
)
_VIDEO_META_KEYS = {
    "og:video",
    "og:video:url",
    "og:video:secure_url",
    "twitter:player",
    "twitter:player:stream",
}
_TRACKING_HOST_HINTS = (
    "doubleclick.",
    "google-analytics.",
    "googletagmanager.",
    "analytics.",
    "pixel.",
    "adservice.",
)
_LOW_VALUE_HINTS = (
    "background",
    "banner",
    "advert",
    "/ads/",
    "/ad/",
    "analytics",
    "tracking",
    "pixel",
)
_SOCIAL_HOSTS = {
    "youtube": ("youtube.com", "youtube-nocookie.com", "youtu.be"),
    "vimeo": ("vimeo.com",),
    "tiktok": ("tiktok.com",),
    "dailymotion": ("dailymotion.com", "dai.ly"),
    "facebook": ("facebook.com", "fb.watch"),
    "instagram": ("instagram.com",),
    "twitch": ("twitch.tv",),
}


@dataclass(frozen=True)
class VideoCandidate:
    url: str
    provider: str
    source_kind: str
    title: str = ""
    score: float = 0.0


def _provider_for_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for provider, hosts in _SOCIAL_HOSTS.items():
        if any(host == known or host.endswith("." + known) for known in hosts):
            return provider
    return host or "web"


def _normalize_embedded_text(value: str) -> str:
    return (
        html_lib.unescape(str(value or ""))
        .replace("\\u002F", "/")
        .replace("\\u002f", "/")
        .replace("\\x2F", "/")
        .replace("\\x2f", "/")
        .replace("\\/", "/")
    )


def _normalize_url(raw: str, base_url: str) -> str | None:
    value = _normalize_embedded_text(raw).strip().strip('"\'()[]{};,')
    if not value:
        return None
    if value.startswith("//"):
        value = "https:" + value
    absolute = urljoin(base_url, value)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return absolute


def _media_extension(url: str) -> str:
    path = (urlparse(url).path or "").lower()
    return next((extension for extension in _MEDIA_EXTENSIONS if path.endswith(extension)), "")


def _known_video_platform(url: str) -> bool:
    return _provider_for_url(url) in _SOCIAL_HOSTS


def _tracking_or_ad_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    lowered = url.lower()
    return any(token in host for token in _TRACKING_HOST_HINTS) or any(token in lowered for token in _LOW_VALUE_HINTS)


def _score_candidate(
    url: str,
    source_kind: str,
    *,
    muted: bool = False,
    autoplay: bool = False,
    loop: bool = False,
    width: int | None = None,
    height: int | None = None,
) -> float:
    base_scores = {
        "iframe": 112.0,
        "og_video": 108.0,
        "video": 104.0,
        "source": 100.0,
        "network": 98.0,
        "script": 72.0,
    }
    score = base_scores.get(source_kind, 70.0)
    extension = _media_extension(url)
    if extension in {".m3u8", ".mpd"}:
        score += 3.0
    elif extension in {".mp4", ".webm", ".mov", ".m4v"}:
        score += 2.0
    if _known_video_platform(url):
        score += 5.0
    if muted:
        score -= 8.0
    if autoplay:
        score -= 8.0
    if loop:
        score -= 7.0
    if width is not None and height is not None and width <= 160 and height <= 120:
        score -= 45.0
    if _tracking_or_ad_url(url):
        score -= 45.0
    return score


def _int_attr(value) -> int | None:
    try:
        match = re.search(r"\d+", str(value or ""))
        return int(match.group(0)) if match else None
    except Exception:
        return None


def _dedupe_rank(rows: Iterable[VideoCandidate], *, limit: int | None = None) -> list[VideoCandidate]:
    best: dict[str, VideoCandidate] = {}
    for row in rows:
        previous = best.get(row.url)
        if previous is None or (row.score, bool(row.title)) > (previous.score, bool(previous.title)):
            best[row.url] = row
    ranked = sorted(best.values(), key=lambda row: (-row.score, row.url))
    return ranked if limit is None else ranked[: max(0, int(limit))]


def _candidate(
    raw_url: str,
    base_url: str,
    source_kind: str,
    *,
    title: str = "",
    muted: bool = False,
    autoplay: bool = False,
    loop: bool = False,
    width: int | None = None,
    height: int | None = None,
) -> VideoCandidate | None:
    url = _normalize_url(raw_url, base_url)
    if not url:
        return None
    return VideoCandidate(
        url=url,
        provider=_provider_for_url(url),
        source_kind=source_kind,
        title=str(title or "").strip(),
        score=_score_candidate(
            url,
            source_kind,
            muted=muted,
            autoplay=autoplay,
            loop=loop,
            width=width,
            height=height,
        ),
    )


def _extract_candidates_from_html(base_url: str, html: str) -> list[VideoCandidate]:
    if not str(html or "").strip():
        return []
    soup = BeautifulSoup(str(html), "lxml")
    rows: list[VideoCandidate] = []

    for meta in soup.find_all("meta"):
        key = str(meta.get("property") or meta.get("name") or "").strip().lower()
        if key not in _VIDEO_META_KEYS:
            continue
        raw = str(meta.get("content") or "").strip()
        row = _candidate(raw, base_url, "og_video", title=key)
        if row:
            rows.append(row)

    for video in soup.find_all("video"):
        attrs_text = " ".join(str(value) for value in (video.get("id"), video.get("class"), video.get("aria-label")) if value)
        muted = video.has_attr("muted")
        autoplay = video.has_attr("autoplay")
        loop = video.has_attr("loop")
        width = _int_attr(video.get("width"))
        height = _int_attr(video.get("height"))
        raw = str(video.get("src") or "").strip()
        if raw:
            row = _candidate(
                raw,
                base_url,
                "video",
                title=attrs_text,
                muted=muted,
                autoplay=autoplay,
                loop=loop,
                width=width,
                height=height,
            )
            if row:
                rows.append(row)
        for source in video.find_all("source"):
            raw_source = str(source.get("src") or "").strip()
            row = _candidate(
                raw_source,
                base_url,
                "source",
                title=str(source.get("title") or attrs_text),
                muted=muted,
                autoplay=autoplay,
                loop=loop,
                width=width,
                height=height,
            )
            if row:
                rows.append(row)

    # Sources outside a <video> can still be used by custom players.
    for source in soup.find_all("source"):
        if source.find_parent("video") is not None:
            continue
        row = _candidate(str(source.get("src") or ""), base_url, "source", title=str(source.get("title") or ""))
        if row:
            rows.append(row)

    for iframe in soup.find_all("iframe"):
        raw = str(iframe.get("src") or "").strip()
        normalized = _normalize_url(raw, base_url)
        if not normalized:
            continue
        if not (_known_video_platform(normalized) or _media_extension(normalized)):
            continue
        row = _candidate(
            normalized,
            base_url,
            "iframe",
            title=str(iframe.get("title") or iframe.get("aria-label") or ""),
            width=_int_attr(iframe.get("width")),
            height=_int_attr(iframe.get("height")),
        )
        if row:
            rows.append(row)

    # Custom players often place media URLs in JSON/script attributes. Keep this
    # deliberately extension-based so normal navigation/tracking URLs are ignored.
    normalized_text = _normalize_embedded_text(str(html))
    pattern = re.compile(
        r"(?P<url>(?:https?:)?//[^\s\"'<>]+?\.(?:mp4|webm|mov|m4v|m3u8|mpd)(?:\?[^\s\"'<>]*)?|(?:\.\.?/|/)[^\s\"'<>]+?\.(?:mp4|webm|mov|m4v|m3u8|mpd)(?:\?[^\s\"'<>]*)?)",
        re.I,
    )
    for match in pattern.finditer(normalized_text):
        row = _candidate(match.group("url"), base_url, "script")
        if row:
            rows.append(row)

    return _dedupe_rank(rows)


def _fetch_static_html(url: str, timeout: int = 20) -> str:
    response = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
        timeout=max(5, int(timeout)),
        allow_redirects=True,
    )
    response.raise_for_status()
    content_type = str(response.headers.get("content-type") or "").lower()
    if content_type and not any(token in content_type for token in ("html", "text", "json", "javascript")):
        return ""
    return response.text or ""


def _discover_browser_evidence(url: str, timeout: int = 20) -> tuple[str, list[tuple[str, str]]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "", []

    try:
        from .browser_search import _launch_chromium
    except Exception:
        _launch_chromium = None

    responses: list[tuple[str, str]] = []
    page_html = ""
    try:
        with sync_playwright() as playwright:
            browser = _launch_chromium(playwright) if _launch_chromium else playwright.chromium.launch(headless=True)
            if browser is None:
                return "", []
            try:
                page = browser.new_page(user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36"
                ))

                def record_response(response):
                    try:
                        response_url = str(getattr(response, "url", "") or "")
                        headers = response.headers
                        content_type = str(headers.get("content-type") or "").lower()
                    except Exception:
                        return
                    if response_url:
                        responses.append((response_url, content_type))

                page.on("response", record_response)
                page.goto(url, wait_until="domcontentloaded", timeout=max(5, int(timeout)) * 1000)
                page.wait_for_timeout(1300)
                try:
                    page.evaluate("window.scrollTo(0, Math.min(document.body.scrollHeight, 2200))")
                    page.wait_for_timeout(450)
                except Exception:
                    pass
                try:
                    page_html = page.content()
                except Exception:
                    page_html = ""
            finally:
                browser.close()
    except Exception:
        return "", []
    return page_html, responses[:250]


def _network_candidates(base_url: str, evidence: Iterable[tuple[str, str]]) -> list[VideoCandidate]:
    rows: list[VideoCandidate] = []
    for raw_url, raw_content_type in evidence:
        url = _normalize_url(raw_url, base_url)
        if not url:
            continue
        content_type = str(raw_content_type or "").lower()
        if not (_media_extension(url) or any(token in content_type for token in _MEDIA_CONTENT_TYPES)):
            continue
        row = _candidate(url, base_url, "network")
        if row and not _tracking_or_ad_url(row.url):
            rows.append(row)
    return rows


def discover_video_candidates(url: str, *, timeout: int = 20, limit: int = 8) -> list[VideoCandidate]:
    base_url = _normalize_url(url, url)
    if not base_url:
        return []

    try:
        static_html = _fetch_static_html(base_url, timeout=timeout)
    except Exception:
        static_html = ""
    rows = _extract_candidates_from_html(base_url, static_html)

    # A first-party player/embed/manifest already gives us a strong candidate.
    # Avoid launching Chromium unless static evidence is absent or weak.
    if not rows or rows[0].score < 90.0:
        browser_html, response_evidence = _discover_browser_evidence(base_url, timeout=timeout)
        rows.extend(_extract_candidates_from_html(base_url, browser_html))
        rows.extend(_network_candidates(base_url, response_evidence))

    return _dedupe_rank(rows, limit=max(1, int(limit)))
