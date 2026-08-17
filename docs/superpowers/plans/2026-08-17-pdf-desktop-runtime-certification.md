# PDF Desktop Runtime Certification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining gap between the certified P60 PDF engine and what a user can observe from the Windows desktop by exposing live query/document telemetry, persistent per-product counts and folders in Ejecutar, and a packaged-entrypoint smoke that proves physical PDF files are produced.

**Architecture:** Keep P60 search/ranking/identity/query-budget behavior unchanged. Extend only the observability boundary: convert existing `PdfSearchTrace` query events into live callbacks, render those callbacks in `PdfDesktopE2EMixin`, expose a compact PDF runtime panel in the existing Ejecutar progress area, and add a diagnostic mode reachable through the same `run_desktop.py` entrypoint used by `ProductIntelligence.exe`. The diagnostic writes machine-readable evidence and verifies retained `.pdf` files; it does not replace the normal GUI path.

**Tech Stack:** Python 3.12, Tkinter, pytest, PyInstaller, GitHub Actions.

## Global Constraints

- Do not change P60 ranking, identity resolution policy, source ordering, or the global hard maximum of 8 PDF search queries per product.
- Do not add SKU-specific production logic or hardcoded successful PDF results.
- Preserve Web/HTML, OCR.Space, Mistral, multimedia, prices, Mercado Libre, updater and Excel behavior.
- New observability must be additive and must not invoke OCR/Mistral during PDF discovery/review.
- Physical PDF certification must assert actual `.pdf` files exist, not only `validated_count > 0` or a directory path.
- Do not merge/release until same-SHA regression, Windows build and packaged PDF runtime smoke are green.

---

### Task 1: Prove the missing live-query and desktop-event contract (RED)

**Files:**
- Create: `tests/test_pdf_desktop_runtime_visibility.py`
- Modify: `tests/test_pdf_pdp_live_observability.py` only if the existing file is the more focused home for trace-to-live callback coverage.

**Interfaces:**
- Consumes: `discover_validated_review_pdfs_live(..., on_event=...)`, `PdfDesktopE2EMixin._apply_pdf_live_event(index, event)`.
- Produces: failing tests that require `query` events with `position/limit/query`, visible identity/candidate/download/accepted/rejected detail, and a per-product final summary.

- [ ] Add a test that makes discovery emit `PDF_SEARCH_QUERY` through the real trace and asserts the live callback receives `type=query`, `position=1`, `limit=8` and the query text.
- [ ] Add a test that feeds query/identity/candidate/download/validated/rejected/final events through the final desktop mixin and asserts the global log contains the concrete URL/file/reason/count data rather than generic stage labels.
- [ ] Run the targeted tests on the branch and verify they fail because v0.10.33 does not expose these details live.

### Task 2: Bridge existing P60 trace events into live desktop telemetry (GREEN)

**Files:**
- Modify: `src/product_intelligence/live_pdf_discovery.py`
- Modify: `src/product_intelligence/pdf_desktop_e2e.py`
- Test: `tests/test_pdf_desktop_runtime_visibility.py`

**Interfaces:**
- Consumes: existing `PDF_SEARCH_QUERY`, `identity`, `candidate`, `download`, `validated`, `rejected`, `duplicate`, `done/final_result` data.
- Produces: additive UI events/log lines; no change to search decisions.

- [ ] In `LiveTrace.emit`, forward `PDF_SEARCH_QUERY` as a live `query` event and number it against `ReviewQueryBudget.limit` without changing budget consumption.
- [ ] Include `inspection.local_path` on completed download/validated telemetry so the desktop can show the physical file.
- [ ] Render explicit lines such as `QUERY 3/8`, `IDENTIDAD`, `ENCONTRADO`, `DESCARGANDO`, `ACEPTADO`, `RECHAZADO`, and `FIN`, always including the concrete product/url/path/reason available in the event.
- [ ] Keep progress monotonic and never infer success before validation.
- [ ] Run targeted tests and verify GREEN.

### Task 3: Put PDF state where the user started the run

**Files:**
- Modify: `src/product_intelligence/pdf_desktop_e2e.py`
- Test: `tests/test_pdf_desktop_runtime_visibility.py`
- Modify: `.github/workflows/build-windows.yml` smoke assertions.

**Interfaces:**
- Consumes: the same live event state from Task 2.
- Produces: a compact Ejecutar-side PDF panel with query/counter status, dedicated PDF progress and `Abrir carpeta PDFs` action.

- [ ] Override the existing progress installer additively and create `pdf_execute_status`, `pdf_execute_counts`, `pdf_execute_progress_bar/value`, and `pdf_execute_open_folder_button` on the Run workspace.
- [ ] Update those variables from live events: query `n/8`, found, downloaded, validated, rejected, current action and selected/current product.
- [ ] Preserve results per product and render a cumulative summary as products finish review.
- [ ] Keep the existing Revisión PDF button and preview; do not duplicate or replace review functionality.
- [ ] Extend the Windows final-shell smoke to assert the new Run-side controls are present.

### Task 4: Certify physical PDFs through the packaged entrypoint

**Files:**
- Create: `src/product_intelligence/pdf_packaged_smoke.py`
- Modify: `run_desktop.py`
- Create: `tests/test_pdf_packaged_smoke_contract.py`
- Modify: `.github/workflows/build-windows.yml`

**Interfaces:**
- Consumes: `search_product_pdfs_by_part_number` and the same package modules frozen into `ProductIntelligence.exe`.
- Produces: `--pdf-e2e-smoke <output-dir> [part numbers...]`, a JSON report and retained `.pdf` files; non-zero exit if no validated physical PDF exists or query budget is exceeded.

- [ ] Write a failing contract test for argument routing from `run_desktop.py` before `managed_main()` and for the smoke report schema.
- [ ] Implement a small diagnostic runner that invokes the production P60 entrypoint, records resolved identity/query count/counts/paths, and verifies every reported accepted path exists and ends in `.pdf`.
- [ ] Add a post-PyInstaller Windows step that runs `dist/ProductIntelligence/ProductIntelligence.exe --pdf-e2e-smoke <temp-output> JBLQ350WLBLKAM` and fails unless the report says PASS and at least one physical PDF exists.
- [ ] Upload the small JSON/report/PDF evidence directory separately from the 593 MB application artifact for inspection.

### Task 5: Same-SHA verification and release decision

**Files:**
- No version bump unless behavior changes require a new distributable version and all gates are green.

**Interfaces:**
- Produces: evidence for merge/release decision.

- [ ] Run full pytest on the exact PR SHA and record the pass count.
- [ ] Confirm the existing three-product P60 smoke remains green and <=8 queries/product.
- [ ] Confirm the Windows build smoke, packaged-entrypoint PDF smoke, and physical-file assertions are green on the same SHA.
- [ ] Inspect the PR diff to ensure no ranking/identity/source-order logic changed.
- [ ] Only then decide whether to merge and whether a version bump beyond v0.10.33 is warranted.