# Social Video Downloader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a URL-driven social/video downloader to the existing Multimedia tab that produces verified local MP4 files and displays them in the current gallery.

**Architecture:** Create a Tk-free downloader service using the `yt-dlp` Python API. The desktop layer owns threading, state and gallery rendering. FFmpeg is resolved from the bundled `imageio-ffmpeg` executable first and PATH second so the Windows bundle remains self-contained.

**Tech Stack:** Python 3.12, yt-dlp, imageio-ffmpeg/FFmpeg, Tkinter, pytest, PyInstaller, GitHub Actions.

## Global Constraints
- Existing automatic Multimedia discovery must remain unchanged.
- Manual social download accepts only `http://` or `https://` URLs.
- No DRM, paywall or authentication bypass.
- Successful output must be a non-empty `.mp4` file.
- UI work stays on the Tk thread; downloads run on a worker thread.
- Site-specific URLs or product IDs must not be hardcoded into production code.
- Failures are explicit and do not break Excel or existing Multimedia discovery.

---

### Task 1: Downloader service

**Files:**
- Create: `src/product_intelligence/social_video_downloader.py`
- Create: `tests/test_social_video_downloader.py`

**Interfaces:**
- Produces: `VideoDownloadResult`, `VideoDownloadError`, `build_format_selector(quality)`, `download_social_video(url, output_dir, quality='best', on_progress=None)`.

- [ ] Write failing tests for URL validation, quality selectors, ffmpeg resolution, verified MP4 output and normalized yt-dlp failures.
- [ ] Run `python -m pytest tests/test_social_video_downloader.py -q` and confirm RED because module/API does not exist.
- [ ] Implement the service with `yt_dlp.YoutubeDL`, collision-safe output templates, MP4 merge/remux, progress hook and final file verification.
- [ ] Re-run focused tests and confirm GREEN.
- [ ] Commit the service + tests.

### Task 2: Multimedia desktop integration

**Files:**
- Modify: `src/product_intelligence/media_desktop.py`
- Modify: `src/product_intelligence/media_progress_desktop.py` only if progress mirroring needs a new event type.
- Create: `tests/test_social_video_desktop_contract.py`

**Interfaces:**
- Consumes: `download_social_video(...)`.
- Produces: URL entry, quality selector, Download MP4 button, worker thread and `social_video_done`/`social_video_error` UI events.

- [ ] Write a failing source/UI contract test requiring the new panel and worker method.
- [ ] Verify RED.
- [ ] Add the panel below the existing action row without changing product discovery controls.
- [ ] On success call `_add_media_card` with `media_type='video'`, `local_path`, source URL and provider.
- [ ] On error restore controls and show a readable status/message without altering `_media_running` discovery state.
- [ ] Run focused desktop tests and existing media desktop tests.
- [ ] Commit UI integration.

### Task 3: Windows packaging and dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `ProductIntelligence.spec` only if PyInstaller does not automatically collect the FFmpeg binary.
- Modify/Create tests covering bundle dependency contract.

**Interfaces:**
- Desktop extra includes `yt-dlp` and `imageio-ffmpeg`.
- Service resolves `imageio_ffmpeg.get_ffmpeg_exe()` before PATH.

- [ ] Add a failing dependency/bundle contract test.
- [ ] Verify RED.
- [ ] Add dependencies and any minimal PyInstaller data/binary collection required.
- [ ] Verify focused tests and normal CI.
- [ ] Commit packaging change.

### Task 4: Live smoke and release gate

**Files:**
- Create: `.github/workflows/social-video-download-smoke.yml`
- Add a small smoke script under `scripts/` if useful.

**Interfaces:**
- Runs the production downloader service against a small public downloader-test video and verifies a non-empty `.mp4`.

- [ ] Add a manually runnable/PR smoke workflow that installs desktop dependencies and invokes `download_social_video` against a public test URL.
- [ ] Keep this live-network smoke separate from deterministic CI so temporary platform blocking is observable rather than masking code regressions.
- [ ] Run workflow and inspect artifact/output.
- [ ] Run full CI and Windows build/release smoke before merge.
- [ ] Merge only if deterministic CI and Windows packaging pass; report live-site smoke separately if the host blocks CI traffic.
