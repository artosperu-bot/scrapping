# Hybrid Video Discovery v0.10.32 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the packaged Windows app reliably download YouTube/social videos and videos embedded in ordinary public webpages, with bundled FFmpeg and generic page discovery.

**Architecture:** Keep `social_video_downloader.py` as the single downloader/normalizer. Add an isolated `video_page_discovery.py` that discovers and ranks media candidates from static HTML and Playwright-rendered pages. Direct `yt-dlp` remains first; page discovery is only a fallback for unsupported/generic page URLs. Ambiguous pages surface a small candidate list to the desktop UI.

**Tech Stack:** Python 3.12, yt-dlp, imageio-ffmpeg, requests, BeautifulSoup/lxml, Playwright Chromium, Tkinter, PyInstaller, pytest.

## Global Constraints

- Release version is exactly `0.10.32` after QA.
- Preserve TikTok and current direct URL behavior.
- Public HTTP/HTTPS only.
- One video per action; playlists disabled.
- No DRM bypass, authentication bypass or cookie harvesting.
- Do not modify PDF discovery, OCR, Mercado Libre, Excel generation or product multimedia search.
- Production changes follow RED → GREEN TDD.

---

### Task 1: Fix bundled FFmpeg handoff

**Files:**
- Modify: `tests/test_social_video_downloader.py`
- Modify: `src/product_intelligence/social_video_downloader.py`

**Interfaces:**
- Consumes: `resolve_ffmpeg_exe() -> str | None`
- Produces: yt-dlp option `ffmpeg_location` containing the exact executable path.

- [ ] **Step 1: Write failing regression test**

Add a test whose fake `resolve_ffmpeg_exe()` returns a nonstandard imageio binary such as `C:/bundle/ffmpeg-win64-v7.0.exe`, invoke `download_social_video()`, and assert `YoutubeDL` receives that exact string in `options['ffmpeg_location']`, not its parent directory.

- [ ] **Step 2: Run focused test and verify RED**

Run: `python -m pytest tests/test_social_video_downloader.py -q`

Expected: new assertion fails because current code passes the parent directory.

- [ ] **Step 3: Implement minimal fix**

Set `options['ffmpeg_location'] = ffmpeg_exe` when a resolved executable exists.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_social_video_downloader.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

Commit message: `fix: pass bundled ffmpeg executable to yt-dlp`

---

### Task 2: Add generic webpage video discovery

**Files:**
- Create: `src/product_intelligence/video_page_discovery.py`
- Create: `tests/test_video_page_discovery.py`

**Interfaces:**
- Produces: `VideoCandidate(url: str, provider: str, source_kind: str, title: str, score: float)`
- Produces: `discover_video_candidates(url: str, *, timeout: int = 20, limit: int = 8) -> list[VideoCandidate]`
- Internal helpers normalize, deduplicate and rank URLs.

- [ ] **Step 1: Write RED tests for static HTML extraction**

Fixtures must cover `<video src>`, nested `<source>`, YouTube/Vimeo iframe, `og:video`, `.m3u8`, `.mpd`, duplicate URLs and an obvious tiny/background media candidate.

Assertions: valid sources are normalized with `urljoin`, duplicates collapse, primary/embed candidates rank above background media, non-http(s) URLs are rejected.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_video_page_discovery.py -q`

Expected: import/function missing.

- [ ] **Step 3: Implement static discovery**

Use `requests` + BeautifulSoup. Parse video/source/iframe/meta/script/html text. Recognize direct video extensions and HLS/DASH manifests. Keep ranking generic and deterministic.

- [ ] **Step 4: Run tests and verify GREEN for static layer**

Run: `python -m pytest tests/test_video_page_discovery.py -q`

- [ ] **Step 5: Add RED dynamic-browser contract test**

Monkeypatch a small Playwright-facing helper so a page that exposes no static media but yields a rendered `<video>`/iframe or `.m3u8` response becomes discoverable. Assert Playwright is only requested after static candidates are insufficient.

- [ ] **Step 6: Implement Playwright fallback**

Capture rendered DOM plus response URLs/content types, reusing the packaged Chromium pattern already used in `browser_search.py`.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_video_page_discovery.py -q`

- [ ] **Step 8: Commit**

Commit message: `feat: discover video sources from public webpages`

---

### Task 3: Connect direct yt-dlp to page fallback

**Files:**
- Modify: `src/product_intelligence/social_video_downloader.py`
- Modify: `tests/test_social_video_downloader.py`

**Interfaces:**
- Add: `VideoSelectionRequired(VideoDownloadError)` carrying `candidates: tuple[VideoCandidate, ...]`
- `download_social_video()` remains the public entrypoint.

- [ ] **Step 1: Write RED fallback tests**

Test A: direct yt-dlp raises `UnsupportedError`; page discovery returns one candidate; downloader retries that candidate and returns verified MP4.

Test B: direct yt-dlp raises a login/private error; page discovery must not run.

Test C: page discovery returns two near-equal strong candidates; raise `VideoSelectionRequired` with a short ranked candidate tuple instead of silently picking an arbitrary video.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_social_video_downloader.py -q`

- [ ] **Step 3: Refactor single-attempt downloader internally**

Extract an internal `_download_with_yt_dlp(...)` so direct and discovered candidate URLs use identical format selection, FFmpeg, progress and MP4 verification.

- [ ] **Step 4: Implement selective fallback**

Only unsupported/generic page outcomes trigger `discover_video_candidates()`. Preserve normalized login/private, DRM, geo, rate-limit and FFmpeg errors without fallback.

- [ ] **Step 5: Verify GREEN**

Run: `python -m pytest tests/test_social_video_downloader.py tests/test_video_page_discovery.py -q`

- [ ] **Step 6: Commit**

Commit message: `feat: fallback from webpage URLs to discovered video sources`

---

### Task 4: Desktop candidate selection and status

**Files:**
- Modify: `src/product_intelligence/media_desktop.py`
- Modify: `src/product_intelligence/social_video_visibility.py`
- Modify: `tests/test_social_video_desktop_contract.py`
- Modify: `tests/test_social_video_visible_in_final_media_ui.py`

**Interfaces:**
- Worker emits `social_video_choices` with candidate records when `VideoSelectionRequired` occurs.
- Main Tk thread renders a compact modal/list and restarts download for the chosen candidate URL.

- [ ] **Step 1: Write RED UI contract tests**

Assert the worker distinguishes selection-required from fatal errors and that the Tk event-drain path handles `social_video_choices` without touching Tk from the worker thread.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_social_video_desktop_contract.py tests/test_social_video_visible_in_final_media_ui.py -q`

- [ ] **Step 3: Implement selection flow**

Show title/provider/source-kind for at most 8 candidates. On selection, place the candidate URL in the existing URL field and call the existing `_start_social_video_download()` path. On cancel, restore button/state without an error popup.

- [ ] **Step 4: Update UI copy**

Describe support as direct video/social URL or a public webpage containing an embedded video; keep explicit private/login/DRM limitations.

- [ ] **Step 5: Verify GREEN**

Run: `python -m pytest tests/test_social_video_desktop_contract.py tests/test_social_video_visible_in_final_media_ui.py -q`

- [ ] **Step 6: Commit**

Commit message: `feat: let desktop choose among webpage video candidates`

---

### Task 5: Smoke, packaging contract and version 0.10.32

**Files:**
- Modify: `scripts/social_video_download_smoke.py`
- Modify: `.github/workflows/social-video-download-smoke.yml`
- Modify: `ProductIntelligence.spec` only if packaging verification proves the new module/binary is omitted.
- Modify: `src/product_intelligence/version.py`
- Modify: `src/product_intelligence/__init__.py`
- Modify: `pyproject.toml`
- Modify: version assertions in tests.

**Interfaces:**
- Social Video smoke must validate exact FFmpeg resolution and generic page discovery contracts without relying solely on mocks.

- [ ] **Step 1: Extend smoke contract before version bump**

The smoke must assert `resolve_ffmpeg_exe()` returns an existing non-empty file and validate the discovery parser against a deterministic local/public-page fixture path used by the script. Do not require a third-party site to remain stable for CI correctness.

- [ ] **Step 2: Run full regression on feature SHA**

Run: `python -m pytest -q`

Expected: all tests green.

- [ ] **Step 3: Bump exactly one patch**

Set all version sources from `0.10.31` to `0.10.32` and update exact version tests.

- [ ] **Step 4: Run full regression again**

Run: `python -m pytest -q`

- [ ] **Step 5: Open PR against `release/windows` and wait for same-SHA gates**

Required: CI success, Social Video Download Smoke success, Windows build success, and no regression in existing PDF Review/Integration workflows that are triggered by shared files.

- [ ] **Step 6: Merge only after all same-SHA gates are green**

Use expected head SHA to prevent merging a moved PR.

- [ ] **Step 7: Verify release workflow**

The push to `release/windows` must build and publish GitHub Release `v0.10.32` with `ProductIntelligence-Windows.zip` and `ProductIntelligence-Windows.sha256`.

- [ ] **Step 8: Final evidence**

Record final merge SHA, test count, workflow run IDs/conclusions, release tag, ZIP size and SHA256 digest.
