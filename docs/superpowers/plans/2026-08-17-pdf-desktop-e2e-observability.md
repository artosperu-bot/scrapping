# PDF Desktop End-to-End Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every PDF found/validated by the P60 identity-first engine is visible in the Windows desktop workflow through persistent files, global logs, progress state, and an obvious folder entry point.

**Architecture:** Keep the certified P60 search/ranking/8-query budget unchanged. Fix the integration boundaries around it: persist direct-document downloads under the execution output root; bridge pre-run PDF Review events into the existing global log/progress observability; expose the PDF folder; and certify the real desktop execution contract rather than only the backend search function.

**Tech Stack:** Python 3.12, Tkinter, pytest, PyInstaller, GitHub Actions.

## Global Constraints

- Preserve P60 global hard maximum of 8 PDF search queries per product end-to-end.
- Do not change PDF ranking/identity policy unless a test proves it is required.
- OCR/Mistral must remain disabled during PDF discovery/review and only run after accepted evidence enters execution.
- Preserve Web, multimedia, prices, Mercado Libre, Excel seller/marketplace protections and updater behavior.
- Do not bump from 0.10.32 until functional QA is green.
- No merge/release until same-SHA CI, PDF desktop E2E smoke and Windows build are green.

---

### Task 1: Reproduce the missing persistent PDF contract

**Files:**
- Modify: `tests/test_pdf_runtime_dataflow_contract.py`
- Modify: `tests/test_pdf_review_runtime_gate.py` or the closest existing PDF review desktop contract test.

**Interfaces:**
- Consumes: `batch.scrape_item`, `document_ingestion.process_pdf_document`, `RealPdfReviewApp.run`.
- Produces: RED tests proving direct P60 documents currently disappear into temporary directories and pre-run review activity is absent from global logs/progress.

- [ ] Add a test where identity-first discovery returns one validated PDF and assert the real batch path supplies a persistent `download_dir` under `<output>/pdf_evidence/<product>`.
- [ ] Run the targeted test and confirm it fails on v0.10.32.
- [ ] Add a desktop contract test asserting the review gate emits an explicit global pre-run message and progress stage before returning.
- [ ] Run it and confirm RED.

### Task 2: Persist direct adaptive PDFs

**Files:**
- Modify: `src/product_intelligence/batch.py`
- Modify: `src/product_intelligence/document_ingestion.py` only if metadata needs to expose the retained local path.
- Test: `tests/test_pdf_runtime_dataflow_contract.py`

**Interfaces:**
- Consumes: existing `process_pdf_document(..., download_dir=...)` support.
- Produces: deterministic directory `<output_root>/pdf_evidence/<safe-product-key>/` for direct adaptive PDF downloads used by execution.

- [ ] Pass a product-specific persistent document directory from `scrape_item` into `_ingest_direct_documents`.
- [ ] Pass that directory into `process_pdf_document` so no `TemporaryDirectory` is used for real batch execution.
- [ ] Record retained local path in fetch/evidence metadata without changing evidence admission rules.
- [ ] Run targeted tests and confirm GREEN.

### Task 3: Bridge PDF Review into global logs and progress

**Files:**
- Modify: `src/product_intelligence/real_pdf_review_shell.py`
- Modify: `src/product_intelligence/live_ui_desktop.py`
- Modify: `src/product_intelligence/excel_live_ui.py` only if a new log marker needs parsing.
- Test: PDF review/live UI contract tests.

**Interfaces:**
- Consumes: existing P60 `log` and `on_event` callbacks.
- Produces: global messages prefixed `[PDF REVIEW]`, visible progress stages, and final counts/paths while the main run is paused for review.

- [ ] When Execute is intercepted by review, emit a global message explaining the run is paused and which product is being searched.
- [ ] Forward P60 review search log lines to both the Revisión PDF status widget and the global log.
- [ ] Reflect SEARCH/DOWNLOAD/VALIDATE/DONE events in the existing Excel progress status/counters without invoking OCR/Mistral.
- [ ] On completion emit validated/rejected/downloaded counts and the persistent review folder.
- [ ] Run targeted tests and confirm GREEN.

### Task 4: Make PDF files discoverable by the user

**Files:**
- Modify: `src/product_intelligence/pdf_review_shell.py`
- Test: UI contract test.

**Interfaces:**
- Consumes: current output root and selected product identity.
- Produces: `Abrir carpeta PDFs` action resolving to `<output>/pdf_review/<identifier>` when reviewing and `<output>/pdf_evidence` as fallback.

- [ ] Add a button to Revisión PDF to open the current product PDF folder.
- [ ] If no current product cache exists, open/create the execution PDF evidence root.
- [ ] Keep path handling Windows-safe and use existing `os.startfile`/fallback message conventions.
- [ ] Run UI contract tests and confirm GREEN.

### Task 5: End-to-end regression and release candidate

**Files:**
- Modify: GitHub Actions smoke only if needed to assert desktop-output persistence.
- Modify version files only after all functional gates pass: `src/product_intelligence/version.py`, `src/product_intelligence/__init__.py`, `pyproject.toml` and version-specific tests/workflows.

**Interfaces:**
- Produces: v0.10.33 release candidate with persistent PDFs and truthful desktop observability.

- [ ] Run full pytest suite.
- [ ] Run a fresh PDF integration smoke for Q350, Endurance Run 3 and Tune 530C and assert query budget <=8.
- [ ] Add/execute a desktop E2E persistence smoke that checks actual PDF files under output and visible log markers.
- [ ] Build Windows and verify the final shell, updater and PDF folder behavior contracts.
- [ ] Bump exactly once from 0.10.32 to 0.10.33.
- [ ] Re-run all same-SHA gates before considering merge/release.
