# Social Video Downloader — Multimedia Design

## Goal
Add a separate URL-driven video downloader inside the existing Multimedia tab so a user can paste a TikTok, YouTube, X/Twitter, Vimeo, Instagram or other supported media URL and obtain a local `.mp4` file that is then shown in the existing multimedia gallery.

## Scope
- Manual URL only; no automatic crawling of social feeds.
- General extractor architecture using `yt-dlp`, not site-specific hardcoding.
- Final user-facing artifact should be `.mp4` whenever technically possible.
- `ffmpeg` is used only when merge/remux/transcode is required by the selected source formats.
- No DRM/paywall bypass and no attempt to defeat authentication/access controls.
- The downloader is isolated from product media discovery; failures never break the existing image/video search workflow.

## UI
Inside `7. Fotos y videos`, add a `Descargar video por URL` panel with:
- URL input.
- Quality selector: `Mejor calidad`, `1080p`, `720p`, `480p`.
- `Descargar MP4` button.
- Status/progress text.
- Output path uses the existing `<output_root>/multimedia` tree, optionally grouped under a product identity when one is selected.

On success the downloaded item is injected into the existing gallery as `media_type=video`, with provider, source URL and local path.

## Architecture
Introduce an isolated service module, e.g. `social_video_downloader.py`.

Public contract:
- validate URL and reject non-HTTP(S) input.
- inspect metadata without downloading where possible.
- choose a format policy from the requested quality.
- invoke `yt-dlp` through its Python API rather than shelling out.
- request MP4-compatible video/audio when available.
- use post-processing to merge/remux to MP4 when needed.
- return a typed result containing title, provider/extractor, webpage URL, local path, duration and selected quality.

The desktop layer owns threading and Tk updates; the downloader service must not access Tkinter.

## Format Policy
`Best` means best video up to no explicit ceiling plus best audio, preferring MP4/M4A and falling back to compatible formats with FFmpeg merge/remux.

For bounded qualities, use the highest representation whose height is <= the requested ceiling, again preferring MP4/M4A.

Final success requires an existing non-empty `.mp4` file. A downloaded WebM/MKV is not considered success until remux/conversion completes.

## Errors
Normalize expected errors into user-readable categories:
- unsupported URL/site;
- private/login-required content;
- geo/network/rate limit;
- ffmpeg unavailable;
- no compatible media stream;
- output verification failed.

Never delete an existing user file. Use collision-safe yt-dlp output naming.

## Packaging
Add `yt-dlp` to the desktop dependency profile. Bundle/discover FFmpeg in the Windows release in a deterministic way; the downloader should resolve the packaged executable first and PATH second.

## Testing
1. Unit tests for URL validation, quality-to-format selection, output verification and normalized errors.
2. Integration test against a fake `yt_dlp.YoutubeDL` proving options and callback behavior without network.
3. Desktop contract test proving the Multimedia tab exposes the URL field, quality selector and download button and that a successful result is added as a video card.
4. Live GitHub Actions smoke using a small public downloader-test video, verifying a real non-empty `.mp4` is produced. This smoke is evidence for the supported engine path, not a guarantee that every social network will always be available; site extractors can change upstream.

## Success Criteria
- Existing Multimedia discovery remains unchanged.
- Pasting a supported public video URL can produce a local `.mp4`.
- The UI remains responsive during download.
- The downloaded video appears in the existing gallery.
- Clear failure is shown for unsupported/private/blocked URLs.
- CI and Windows release build pass with no credentials required.
