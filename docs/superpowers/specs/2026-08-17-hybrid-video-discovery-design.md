# Hybrid Video Discovery v0.10.32 — Design

## Goal

Make **Descargar video por URL** work reliably for direct social/video URLs and for ordinary public webpages that contain or embed a playable video, while preserving the existing Multimedia workflow.

## User-approved behavior

1. Try the submitted URL directly with `yt-dlp` first.
2. Use the exact bundled FFmpeg executable when merging/remuxing is required; the user must not install FFmpeg separately.
3. If the direct URL is unsupported as a video, inspect the public webpage for real media sources and embeds.
4. Discover candidates from:
   - `<video>` and `<source>` elements;
   - `iframe` embeds such as YouTube/Vimeo and any URL that `yt-dlp` can resolve;
   - `og:video` / `twitter:player` metadata;
   - direct `.mp4` / `.webm` URLs;
   - HLS `.m3u8` and DASH `.mpd` manifests;
   - JSON/JavaScript/HTML text and browser network responses when the source is rendered dynamically.
5. Rank and deduplicate candidates. Prefer the page's primary video/embed over tiny/background/advertising media.
6. If one candidate is clearly best, download it automatically. If multiple plausible primary videos remain close, expose a short candidate list so the desktop UI can ask the user which one to download.
7. Normalize successful downloads to a verified non-empty MP4.
8. Preserve explicit errors for DRM, login/private content, geo blocks, rate limits and unsupported pages. Do not bypass DRM or authentication controls.

## Architecture

### `social_video_downloader.py`

Owns direct `yt-dlp` execution, quality selection, FFmpeg resolution, output verification and normalized errors. It remains the single download path.

The FFmpeg contract changes from “directory containing the resolver result” to **the exact executable path returned by `imageio_ffmpeg.get_ffmpeg_exe()`**. `yt-dlp` accepts either a binary path or a containing directory; passing the exact path is necessary for imageio-ffmpeg binaries whose filename is not literally `ffmpeg.exe`.

### `video_page_discovery.py`

New isolated discovery module. It does not download media. It receives a webpage URL and returns ranked `VideoCandidate` records.

Discovery is layered:

- cheap static HTTP/HTML extraction first;
- Playwright only when static extraction is insufficient;
- browser DOM plus captured response URLs/content for dynamically injected sources;
- URL normalization/deduplication and candidate scoring in one place.

No product/PDF/price logic is imported into this module.

### Direct → page fallback

`download_social_video()` first executes the existing direct `yt-dlp` path. Only an unsupported/generic-page failure is eligible for webpage discovery. Login, DRM, geo, rate-limit or FFmpeg failures are not hidden by fallback.

Each discovered candidate is then passed back through the same `yt-dlp` download function. Direct media/manifest URLs therefore use the same validation and MP4 normalization as social platforms.

### Ambiguous pages

A new `VideoSelectionRequired` exception carries a small ranked tuple of candidates. `media_desktop.py` handles it on the Tk main thread and shows a compact selection dialog. Choosing a row restarts the same download using the selected candidate URL. Cancelling leaves the page untouched.

## Ranking principles

Positive signals: iframe/player context, `og:video`, `<video>` source, dimensions/primary DOM position when available, YouTube/Vimeo embeds, manifest/direct video extensions, same-page semantic context.

Negative signals: duplicate URLs, known tracking/ad hosts, tiny dimensions, muted/autoplay/background hints, poster/image assets, analytics URLs and non-media MIME types.

The ranking is generic. No hard-coded product, brand, YouTube video ID or target website is allowed.

## Safety and scope

- Public HTTP/HTTPS URLs only.
- One video download per action; playlists remain disabled.
- No cookie harvesting, credential extraction or DRM circumvention.
- Existing TikTok behavior must remain green.
- PDF discovery, OCR, Mercado Libre, Excel generation and product multimedia search are frozen.

## Release gate

Version: **0.10.32**.

A release is allowed only after:

- FFmpeg regression test demonstrates the exact packaged binary path is passed to `yt-dlp`;
- generic static webpage discovery tests pass;
- dynamic/embedded discovery contract tests pass;
- direct social-video tests pass;
- full regression suite passes;
- Social Video Download Smoke passes on the final SHA;
- Windows build produces the executable and standalone updater successfully;
- GitHub Release `v0.10.32` contains the ZIP and SHA256 assets.
