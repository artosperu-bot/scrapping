# Media Downloader Design

## Goal
Add a standalone **Fotos y videos** workflow to the existing Windows desktop application. It must reuse the workbook product identities and existing discovery/media extraction logic, search the web by Part Number/model when needed, allow per-product manual URLs, download validated images and directly downloadable videos, and show newly downloaded media as live thumbnails without changing the Excel-generation workflow.

## Product identity policy
- Primary identity is Part Number / MPN when available, then EAN/UPC/GTIN, then model/name.
- Exact color is not a hard requirement for this media-only workflow. Same-model media may be accepted when the model/product identity is validated.
- Variant/capacity conflicts remain rejection signals when they identify a materially different product.
- Manual URLs are optional and tried first, but are still validated.

## Discovery order
For each product:
1. Manual URLs supplied for that product.
2. Existing `search_web(ProductIdentity)` discovery using exact strong identifiers and brand/model queries across free search providers.
3. Prefer manufacturer/official candidates by existing candidate ranking.
4. Fetch each page with `fetch_page`, starting static and falling back to Playwright when useful; enable lazy-media activation for the media workflow.
5. Run existing `discover_media` against rendered/static HTML plus captured network resources.
6. Accept high-confidence product media first; allow same-model media even if color differs in this dedicated workflow.
7. Fall back to compatible secondary sources when official sources do not provide enough media.

## Download policy
- Images: download HTTP/HTTPS assets that resolve to image content and pass identity/media-role checks.
- Direct video files: download MP4/WebM/MOV where exposed as direct assets.
- HLS (`m3u8`) and hosted embeds (YouTube/Vimeo): save metadata + provider URL + thumbnail/poster when available; do not add a downloader dependency for third-party hosted video.
- Deduplicate by normalized source URL and downloaded content SHA-256.
- Use safe filenames and preserve the original extension when trustworthy.

## Output layout
```
<output>/multimedia/
  fotos/<PART_NUMBER_OR_ID>/
    01.<ext>
    02.<ext>
    metadata.json
  videos/<PART_NUMBER_OR_ID>/
    01.<ext>                  # direct downloadable media only
    metadata.json             # also records hosted/embed video URLs
```

Each metadata entry includes product identity, original URL, page URL, source type, discovery method, media role, confidence, local path when downloaded, content type, byte count and SHA-256 when applicable.

## Desktop UI
Add a new notebook tab **7. Fotos y videos** after Logs. It is independent from **5. Ejecutar**.

The tab contains:
- product selector/list populated from the analyzed Excel;
- optional manual URLs per selected product;
- checkbox to search the web automatically (default on);
- checkbox to prefer official sources (default on; ranking remains deterministic);
- button to process selected product;
- button to process all products;
- status/progress text;
- scrollable live media gallery.

As soon as a downloaded image is available, the worker emits a UI event. The Tk main thread loads a Pillow thumbnail and adds it to the gallery. Video entries show a generated card using poster/thumbnail when available, otherwise a text tile with provider/type. Double-clicking an item opens the local downloaded file when present or the source URL otherwise.

## Isolation
- Do not call the Excel filling pipeline from the media tab.
- Do not mutate workbook content.
- Do not change existing `run_batch` behavior.
- Keep download/orchestration code outside `desktop.py`; desktop only coordinates inputs, background thread and UI events.
- Reuse `discovery.py`, `web_fetch.py` and `media_discovery.py` rather than duplicating scraping logic.

## Components
### `media_downloader.py`
Owns safe download, content validation, hashing, filename generation and metadata persistence.

### `media_workflow.py`
Owns product-level orchestration: URL ordering, page fetching, media discovery, relaxed color policy for the media-only workflow, deduplication, download invocation and progress callbacks.

### `desktop.py`
Adds the independent tab, per-product manual media URLs, background execution and live thumbnails.

## Error handling
- A failed URL is logged and processing continues with the next candidate.
- A failed media download does not fail the whole product.
- 401/403/429/static shells may invoke the existing Playwright fallback.
- Corrupt/non-media HTTP responses are rejected before writing final files.
- UI updates occur only on Tk main thread through the existing queue/drain pattern.

## Testing
- Unit tests for safe folder naming, extension/content-type selection, image/video acceptance, deduplication and metadata writing.
- Workflow tests with monkeypatched search/fetch/download to prove manual URL priority, web-search fallback, same-model/different-color acceptance and per-product isolation.
- Desktop structural tests to ensure the new media tab does not invoke `run_batch` and retains the existing scraping button/flow.
- Existing media regression tests remain green.
