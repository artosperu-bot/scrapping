# Standalone Fotos y Videos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent desktop workflow that discovers, downloads, previews and audits product images/videos per Part Number/model without changing the Excel scraping path.

**Architecture:** Reuse `discovery.search_web`, `web_fetch.fetch_page` and `media_discovery.discover_media`. Add a small downloader/persistence unit and a media orchestration unit. `desktop.py` only supplies product identities/manual URLs, launches a worker thread, consumes callback events and renders thumbnails.

**Tech Stack:** Python 3.10+, requests, BeautifulSoup/lxml, Pillow, Tkinter, Playwright fallback, pytest.

## Global Constraints
- Existing `run_batch` and Excel-generation behavior must remain unchanged.
- Media processing is a separate tab/process.
- Manual product URLs are tried before automatic web discovery.
- Automatic discovery uses exact Part Number/strong identifiers and existing search ranking.
- Color mismatch is not a rejection for this media-only workflow when the same model/product is validated; capacity/material variant conflicts stay protected.
- Third-party hosted video is recorded as metadata/link; only direct media files are downloaded.
- Output is `<output>/multimedia/fotos/<ID>/` and `<output>/multimedia/videos/<ID>/`.
- Live UI updates must execute on the Tk main thread.

---

### Task 1: Downloader and metadata persistence

**Files:**
- Create: `tests/test_media_downloader.py`
- Create: `src/product_intelligence/media_downloader.py`

**Interfaces:**
- Produces `safe_product_key(identity: ProductIdentity) -> str`
- Produces `download_media_item(item: dict, identity: ProductIdentity, output_root: str | Path, *, session: requests.Session | None = None, timeout: int = 30) -> dict`
- Produces `write_media_metadata(output_root: str | Path, identity: ProductIdentity, results: list[dict]) -> None`

- [ ] **Step 1: Write failing tests** for safe directory names, image/direct-video download routing, non-media rejection, and SHA-256 dedup metadata.
- [ ] **Step 2: Run** `pytest tests/test_media_downloader.py -v` and confirm failures are because functions do not exist.
- [ ] **Step 3: Implement minimal downloader** using `requests`, streamed bytes, content-type/extension validation, safe temporary files and SHA-256.
- [ ] **Step 4: Run** `pytest tests/test_media_downloader.py -v` and confirm PASS.
- [ ] **Step 5: Commit** `feat: add validated media downloader`.

### Task 2: Product media workflow

**Files:**
- Create: `tests/test_media_workflow.py`
- Create: `src/product_intelligence/media_workflow.py`

**Interfaces:**
- Consumes `search_web`, `fetch_page`, `discover_media`, downloader functions.
- Produces `run_media_product(identity, output_root, manual_urls=None, auto_search=True, max_pages=8, on_event=None) -> list[dict]`.
- Callback events are dictionaries with `type` in `status|page|media|error|done` and product/media fields.

- [ ] **Step 1: Write failing tests** proving manual URLs come first, search candidates append without duplication, `fetch_page(... activate_lazy_media=True)` is used, same-model/different-color media is accepted by clearing only color for media validation, and hosted embeds remain metadata-only.
- [ ] **Step 2: Run** `pytest tests/test_media_workflow.py -v` and verify RED.
- [ ] **Step 3: Implement orchestration** with per-page exception isolation, candidate ranking order, resource dedup and callback events.
- [ ] **Step 4: Run** `pytest tests/test_media_workflow.py -v` and verify GREEN.
- [ ] **Step 5: Commit** `feat: orchestrate product media discovery`.

### Task 3: Desktop media tab and live thumbnails

**Files:**
- Create: `tests/test_desktop_media_tab.py`
- Modify: `src/product_intelligence/desktop.py`

**Interfaces:**
- Consumes `run_media_product`.
- Reuses `App._identity_for_index`, `product_rows`, `out`, existing queue/threading pattern.
- Adds `media_manual_urls`, media product list, gallery canvas/frame and `_media_events` queue.

- [ ] **Step 1: Write structural failing tests** verifying `desktop.py` builds `7. Fotos y videos`, imports/uses `run_media_product`, and media execution path does not call `run_batch`.
- [ ] **Step 2: Run** `pytest tests/test_desktop_media_tab.py -v` and verify RED.
- [ ] **Step 3: Implement tab** with product selection, optional URLs, automatic-search checkbox, selected/all buttons, status and scrollable gallery.
- [ ] **Step 4: Implement live preview** by polling a dedicated queue on Tk main thread; load image thumbnails with Pillow; show video/link tiles; double-click opens local file or browser URL.
- [ ] **Step 5: Update `analyze_excel`** to repopulate media product list and initialize media URL state without changing `manual_urls` used by the existing scraping workflow.
- [ ] **Step 6: Run** `pytest tests/test_desktop_media_tab.py -v` and targeted existing desktop/preflight tests.
- [ ] **Step 7: Commit** `feat: add live media gallery to desktop`.

### Task 4: Regression verification and packaging compatibility

**Files:**
- Modify only if needed: `ProductIntelligence.spec`, `README.md`

- [ ] **Step 1: Run targeted suite:** `pytest tests/test_v4_media.py tests/test_targeted_excel_and_media.py tests/test_v9_manual_part_numbers.py tests/test_v9_three_headphones_template.py tests/test_media_downloader.py tests/test_media_workflow.py tests/test_desktop_media_tab.py -v`.
- [ ] **Step 2: Run full suite:** `pytest -q`.
- [ ] **Step 3: Inspect PyInstaller spec** and ensure no new non-standard dependency is required beyond already bundled requests/Pillow/Playwright.
- [ ] **Step 4: Update README** with the standalone media workflow and output folders.
- [ ] **Step 5: Commit** `docs: document standalone media workflow`.

## Self-review
- Spec coverage: manual URL, automatic web discovery, official preference, model-over-color policy, direct downloads, hosted-video metadata, live thumbnails, separate process and output hierarchy are each mapped to a task.
- No new Google scraping dependency is introduced; existing multi-provider web discovery is reused.
- No code path requires modification of `run_batch` or Excel mapping.
- Types and callback contract are consistent across Tasks 1–3.
