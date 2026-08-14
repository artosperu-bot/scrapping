# Generic Excel Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fragile Excel-to-product detection with a generic, observable intake layer and move workbook analysis off the Tkinter UI thread without changing SEARCH/scraping behavior.

**Architecture:** Add a focused `excel_intake.py` module that performs sheet/header/row/identity analysis and emits diagnostics plus normalized `BatchItem`-compatible identities. Make `batch.detect_items()` a compatibility adapter over that analyzer. Expose diagnostics through preflight and make desktop analysis asynchronous.

**Tech Stack:** Python 3.10+, openpyxl, dataclasses, regex, Tkinter, pytest.

## Global Constraints
- Base from current `release/windows` after PR #31.
- Do not modify `main`.
- Do not hardcode sheet names, column indexes, categories or marketplaces.
- Do not modify SEARCH/scraping unless a regression proves it necessary.
- Preserve v0.10.4+ canonical/evidence, PDF, Multimedia, Price Intelligence, OCR.space, Mistral and updater behavior.
- One usable identity value must be sufficient for intake.

---

### Task 1: Generic header identity vocabulary
**Files:**
- Create: `src/product_intelligence/excel_intake.py`
- Test: `tests/test_excel_intake_generic.py`

**Interfaces:**
- Produces `normalize_header(label: str) -> str`.
- Produces `identity_header_kind(label: str) -> str | None` with `part_number`, `gtin`, `sku`, `model`, `product_name`, `brand`.

- [ ] Write failing tests covering `Part_Number`, `manufacturer partnumber`, `Modelo #32`, `Model No`, `EAN/UPC`, `código de barras`, `sku_seller`, `Merchant SKU`.
- [ ] Run focused tests and verify RED.
- [ ] Implement separator/accent/case normalization and alias classification.
- [ ] Run focused tests and verify GREEN.

### Task 2: Sheet/header classifier using downstream evidence
**Files:**
- Modify: `src/product_intelligence/excel_intake.py`
- Test: `tests/test_excel_intake_generic.py`

**Interfaces:**
- Produces `analyze_sheet(ws) -> SheetAudit`.
- `SheetAudit` includes title, score, accepted, header_row, raw_headers, normalized_headers, identity_columns, rejection_reason.

- [ ] Write failing tests for one-column Part Number, auxiliary instructions/list sheet, and misleading upper header row.
- [ ] Verify RED.
- [ ] Implement first-30-row scan scoring header semantics + identity-like values below header + repeated row density.
- [ ] Verify GREEN.

### Task 3: Row identity resolver and rejection reasons
**Files:**
- Modify: `src/product_intelligence/excel_intake.py`
- Test: `tests/test_excel_intake_generic.py`

**Interfaces:**
- Produces `WorkbookIntakeResult` containing `products` and `sheet_audits`.
- Product rows expose normalized `ProductIdentity` and row diagnostics.

- [ ] Write failing tests proving a row with only `TE-2128S`, `IPC-S042`, or `JBLQ350WLBLKAM` is accepted; EAN-only and SKU-only fallback are accepted; blank/placeholder rows emit explicit rejection codes.
- [ ] Verify RED.
- [ ] Implement priority `part_number -> gtin -> model -> sku -> product_name` and placeholder filtering.
- [ ] Verify GREEN.

### Task 4: Compatibility adapter in batch
**Files:**
- Modify: `src/product_intelligence/batch.py`
- Test: `tests/test_excel_intake_batch_bridge.py`

**Interfaces:**
- `detect_items(template)` continues returning `list[BatchItem]`.
- SEARCH-facing `scrape_item()` remains unchanged.

- [ ] Write failing bridge tests showing one-column products become `BatchItem` objects with correct sheet/row/identity.
- [ ] Verify RED.
- [ ] Replace legacy detection internals with intake result adaptation while preserving manual mode helpers.
- [ ] Verify GREEN and existing `test_v9_manual_part_numbers.py`.

### Task 5: Preflight observability
**Files:**
- Modify: `src/product_intelligence/preflight.py`
- Test: `tests/test_excel_intake_preflight_audit.py`

**Interfaces:**
- `analyze_workbook()` adds `intake_audit` and per-product `search_requested/search_query` without invoking the web.

- [ ] Write failing tests for accepted/rejected rows and query preview.
- [ ] Verify RED.
- [ ] Expose sheet/header/row diagnostics from intake and use `discovery.build_query(identity)` only to preview the query.
- [ ] Verify GREEN.

### Task 6: Non-blocking desktop analysis
**Files:**
- Modify: `src/product_intelligence/desktop.py`
- Modify: `src/product_intelligence/workspace_desktop.py` only if completion hook is required.
- Test: `tests/test_desktop_excel_analysis_async.py`

**Interfaces:**
- `analyze_excel()` dispatches `analyze_workbook()` on a daemon thread.
- UI mutation occurs only via Tk `after` callback.
- Duplicate analysis while running is rejected/ignored.

- [ ] Write structural/behavioral failing tests that analysis work is spawned on a thread and result application is separated into a UI-thread method.
- [ ] Verify RED.
- [ ] Extract `_apply_analysis_result(data)` and `_apply_analysis_error(exc)` from existing synchronous handler; add `_analysis_running` guard.
- [ ] Update workspace shell to sync products after successful result application rather than immediately after dispatch.
- [ ] Verify GREEN.

### Task 7: Full regression and Windows gate
**Files:**
- No product changes unless a demonstrated regression requires one.

- [ ] Run full PR CI.
- [ ] Compare diff against `release/windows`; confirm no scraping/price/media/PDF/updater changes.
- [ ] Trigger isolated Windows gate using the same temporary branch-trigger technique used for PR #31, then restore workflow YAML.
- [ ] Require regression tests, desktop smoke, PyInstaller build, both EXEs and artifact upload to PASS.
- [ ] Run final CI after workflow restoration.
- [ ] Merge only after all gates are GREEN.
