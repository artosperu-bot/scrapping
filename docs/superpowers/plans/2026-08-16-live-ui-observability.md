# ProductIntelligence v0.10.25 Live UI Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Price, PDF Review, Multimedia, Social Video, Scraping Excel and Audit visibly update while work is in progress, with truthful state and safe Tk threading.

**Architecture:** Preserve the current desktop inheritance chain and engines. Add a small reusable event/state helper, then adapt each existing module to emit/consume incremental events through queues and Tk `after()` only. Keep results scoped by run/product/workspace and retain them across view changes.

**Tech Stack:** Python 3, Tkinter/ttk, `queue.Queue`, `threading`, pytest, GitHub Actions, PyInstaller/Windows release workflows.

## Global Constraints
- Base branch: `release/windows` at `7c04192c9d1ec8ea189aaad229e2973f9aa2bd1c`.
- Current app version remains `0.10.24` until all v0.10.25 gates pass.
- Preserve PR #52 PDF identity bootstrap and reviewed-mode enforcement.
- No direct Tk widget mutation from worker threads.
- No invented percentages, OCR stages, Mistral stages, speed, ETA, byte totals, or source counts.
- No PDF may become evidence before explicit approval in reviewed mode.
- Do not rewrite validated scraping, source validation, identity, price quality, media quality, OCR/Mistral, workspace or updater logic.

---

### Task 1: Shared live-event state contract
**Files:**
- Create: `src/product_intelligence/live_ui_events.py`
- Test: `tests/test_live_ui_events.py`

**Interfaces:**
- Produces `LiveUiState`, `event_key(event)`, `apply_event(state, event)`.
- State retains counters/items/errors per `(module, workspace_id, product_index, run_id)`.

- [ ] Write RED tests proving accepted items dedupe, rejected/error counters advance, unknown fields do not invent progress, and two products/workspaces remain isolated.
- [ ] Run the focused pytest in CI and confirm expected failure because module is missing.
- [ ] Implement the minimal pure-Python state reducer.
- [ ] Run focused tests to green.
- [ ] Commit.

### Task 2: Price live-render contract
**Files:**
- Modify: `src/product_intelligence/price_desktop.py`
- Test: `tests/test_price_live_ui_contract.py`

**Interfaces:**
- Consume current `price_events` queue and existing `offer/status/page/coverage/done/fatal/batch_done` events.
- Add stable visual dedupe and truthful counters/stage text.

- [ ] RED test: enqueue `batch_product -> status -> offer -> done`; assert offer rendering hook executes before final completion hook.
- [ ] RED test: duplicate offer events render one final row and are audit-observable as duplicate skip.
- [ ] RED test: `fatal -> batch_done` restores both buttons and leaves visible ERROR state.
- [ ] Implement minimal event handling changes; do not alter `run_price_product` validation logic.
- [ ] Run focused price tests and existing price tests to green.
- [ ] Commit.

### Task 3: PDF incremental discovery
**Files:**
- Modify: `src/product_intelligence/part_number_pdf_search.py`
- Modify: `src/product_intelligence/real_pdf_review_shell.py`
- Test: `tests/test_pdf_live_ui_contract.py`

**Interfaces:**
- Extend `search_product_pdfs(..., on_event=None)` compatibly.
- Emit `search`, `candidate`, `validated`, `rejected`, `duplicate`, `error`, `done` events with product/run context supplied by caller.

- [ ] RED test: first validated candidate callback occurs before `search_product_pdfs` returns final result.
- [ ] RED test: UI candidate collection receives validated candidate incrementally and does not mark review enforced.
- [ ] RED test: rejected/duplicate candidate affects audit/counters but not selectable candidate list.
- [ ] Implement callbacks in discovery path without invoking OCR/Mistral.
- [ ] Update real PDF shell to queue events and update Tk only on main thread.
- [ ] Run PDF review/discovery regression suites to green.
- [ ] Commit.

### Task 4: Multimedia live gallery
**Files:**
- Modify: `src/product_intelligence/media_progress_desktop.py` or final organized media adapter only where inherited widgets require it.
- Test: `tests/test_media_live_ui_contract.py`

**Interfaces:**
- Reuse existing mirrored media event queue.
- `media` event with a valid downloaded artifact triggers immediate gallery refresh/render before product `done`.

- [ ] RED test: media event updates counters/card hook before done.
- [ ] RED test: rejected media increments rejected/audit state without adding a gallery card.
- [ ] RED test: UI event handler exception is contained and subsequent events continue draining.
- [ ] Implement incremental gallery refresh and real counters.
- [ ] Run existing media tests plus focused UI contract tests to green.
- [ ] Commit.

### Task 5: Social video truthful progress
**Files:**
- Modify: `src/product_intelligence/social_video_downloader.py`
- Modify: UI consumer in `src/product_intelligence/media_desktop.py` / inherited final shell.
- Test: `tests/test_social_video_live_ui_contract.py`

**Interfaces:**
- Progress callback emits only available `downloaded_bytes`, `total_bytes`, `speed`, `eta`, postprocess state, final path and size.

- [ ] RED test: downloader progress hook forwards provided yt-dlp fields and omits unavailable values.
- [ ] RED test: postprocess/verify/completed phases are ordered.
- [ ] RED test: completed MP4 triggers immediate gallery card hook.
- [ ] Implement compatible callbacks and Tk queue consumption.
- [ ] Run social-video smoke/unit tests to green.
- [ ] Commit.

### Task 6: Scraping Excel live stages
**Files:**
- Modify: the existing desktop batch callback path in `src/product_intelligence/desktop.py` / current final inherited shell.
- Modify only the narrowest engine callback points in `batch.py`/`pipeline.py` if a stage is currently unobservable.
- Test: `tests/test_excel_live_ui_contract.py`

**Interfaces:**
- Emit/render real stages IDENTITY, SEARCH, VALIDATE, EXTRACT, PDF, OCR, MISTRAL, SEMANTIC_RESOLUTION, WRITE_EXCEL only when executed.

- [ ] RED test: product status appears before batch completion.
- [ ] RED test: OCR/Mistral OFF produces no fake OCR/MISTRAL event.
- [ ] RED test: partial field/PDF counters update before final batch result.
- [ ] Implement minimal callback propagation and UI counters.
- [ ] Run Excel/intake/PDF strategy regression suites to green.
- [ ] Commit.

### Task 7: Live audit, cross-view preservation and error recovery
**Files:**
- Create or modify narrow final-shell adapter for shared audit/state retention.
- Test: `tests/test_live_ui_state_preservation.py`

**Interfaces:**
- Retain accepted current-run results by workspace/product/module.
- View switches read retained state; new explicit run resets only its scope.

- [ ] RED tests for Price -> Audit -> Price preservation, PDF candidate preservation, media gallery preservation, and workspace/product isolation.
- [ ] RED test for RUNNING -> ERROR -> controls restored -> next run allowed.
- [ ] Implement retained state rendering and reset semantics.
- [ ] Run focused tests to green.
- [ ] Commit.

### Task 8: Release gates and v0.10.25 bump
**Files:**
- Modify: `src/product_intelligence/version.py`
- Add/update release contract test if needed.

- [ ] Run complete CI and relevant Windows packaging workflows on feature branch/PR.
- [ ] Verify UI-1 through UI-5 automated contracts green; do not claim manual visual evidence that CI cannot provide.
- [ ] Bump `APP_VERSION = "0.10.25"` only after all critical automated gates are green.
- [ ] Re-run full CI/Windows packaging after bump.
- [ ] Open/complete PR to `release/windows` only when green.
