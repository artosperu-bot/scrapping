# Product Run Audit and Media Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate deterministic seller SKU output, unified audit events, recovered photo/video coverage, and multi-product certification without regressing the modern desktop or current Peru price engine.

**Architecture:** Keep the existing engines intact and add narrow contracts around them. Seller SKU derivation belongs in Excel/output mapping; audit uses a small normalized event model/collector consumed by the desktop; media recovery separates page identity, media relevance, and download viability with contextual confidence rather than one global threshold. Live workflows certify the exact integration before Windows packaging.

**Tech Stack:** Python 3.12, tkinter/ttk, pytest, Playwright Chromium, openpyxl, existing Product Intelligence modules, GitHub Actions, PyInstaller.

## Global Constraints

- `SKU vendedor = Part Number` is deterministic by default.
- External marketplace seller SKU/publication IDs remain evidence and do not replace the STECH Part Number default.
- Do not remove identity guards or globally lower media confidence to inflate coverage.
- Strong identifiers (MPN/Part Number/EAN/UPC/GTIN) take priority; brand+model is fallback only.
- Preserve modern desktop and current Price Intelligence.
- A product with no valid video must report `NO_RESULT`, never cross-product media.
- Windows artifact must be produced from the same `main` SHA containing all changes.

---

### Task 1: Seller SKU contract

**Files:**
- Modify: `src/product_intelligence/excel_mapper_v8.py` and/or the narrow output derivation helper used by it
- Test: existing Excel mapper tests plus a focused `tests/test_seller_sku_default.py`

**Interfaces:**
- Consumes: normalized product row containing canonical Part Number/MPN.
- Produces: output value for `SKU vendedor` equal to canonical Part Number unless a future explicit override contract exists.

- [ ] **Step 1: Write failing tests** covering `SKU vendedor` blank in template, external seller SKU present, and generic non-JBL products; all must output Part Number.
- [ ] **Step 2: Run focused tests** and confirm RED on current behavior.
- [ ] **Step 3: Implement minimal deterministic derivation** at output mapping boundary, not inside price marketplace evidence.
- [ ] **Step 4: Run focused + Excel regression tests** and confirm PASS.
- [ ] **Step 5: Commit** `feat: default seller sku to part number`.

### Task 2: Unified audit event contract

**Files:**
- Create: `src/product_intelligence/run_audit.py`
- Modify: `src/product_intelligence/modern_desktop.py`
- Modify narrow event adapters in media/price/run desktop integration as needed
- Test: `tests/test_run_audit.py`, modern desktop tests

**Interfaces:**
- Produces: normalized event dict with `timestamp`, `part_number`, `module`, `source`, `url`, `status`, `detail`, `result`.
- Collector supports append, filtering by product/module/status, and export/snapshot for UI.

- [ ] **Step 1: Write failing event normalization/filter tests.**
- [ ] **Step 2: Confirm RED.**
- [ ] **Step 3: Implement focused `RunAudit`/normalizer with allowed modules and statuses from the spec.**
- [ ] **Step 4: Wire existing media and price callbacks into the collector without changing engine semantics.**
- [ ] **Step 5: Upgrade `Auditoría` workspace to show master events with product/module/status filters while preserving specialized Multimedia and Precios pages.**
- [ ] **Step 6: Run audit + UI regression tests.**
- [ ] **Step 7: Commit** `feat: add unified product run audit`.

### Task 3: Reproduce multimedia coverage regression

**Files:**
- Inspect: `src/product_intelligence/media_workflow.py`, `media_discovery.py`, `media_downloader.py`, `web_fetch.py`
- Compare historical commits around successful media smoke runs
- Test/workflow: `.github/workflows/media-integration-smoke.yml`

**Interfaces:**
- Output diagnostic counts by stage: candidate pages, identity-validated pages, discovered images/videos, filtered-by-reason, download success, metadata-only, errors.

- [ ] **Step 1: Identify a historical successful live run and exact commit/product used.**
- [ ] **Step 2: Run/inspect current live smoke on the same identity and collect stage counts.**
- [ ] **Step 3: Compare current code to successful baseline and localize loss to discovery, validation, relevance, URL promotion, or downloader.**
- [ ] **Step 4: Add failing regression tests reproducing the localized cause before changing production logic.**
- [ ] **Step 5: Commit diagnostic tests only if useful independently.**

### Task 4: Recover image/video coverage safely

**Files:**
- Modify only the media modules implicated by Task 3
- Test: media unit/regression tests, anti-cross-product fixtures

**Interfaces:**
- `page_identity`: accepted/rejected with strong-ID evidence or safe descriptive fallback.
- `media_relevance`: image/video role, scope, evidence, contextual confidence.
- `download_viability`: downloadable, metadata-only valid link, or rejection reason.

- [ ] **Step 1: Implement contextual acceptance** for validated official/product pages and strong-ID retailer pages; do not globally reduce `0.95`.
- [ ] **Step 2: Preserve unconditional rejection of related-product/page-asset conflicts.**
- [ ] **Step 3: Restore thumbnail/original promotion and embedded video extraction where regression evidence requires it.**
- [ ] **Step 4: Emit explicit `FOUND`, `REJECTED`, `NO_RESULT`, `ERROR`, `DONE` audit events for image/video stages.**
- [ ] **Step 5: Run media regression and anti-cross-product tests.**
- [ ] **Step 6: Commit** `fix: recover validated product media coverage`.

### Task 5: Multi-product certification

**Files:**
- Add/extend tests and one CI smoke matrix workflow or script using existing fixtures/live-safe identities.

**Interfaces:**
- Matrix categories: laptop, smartphone, audio, cable/accessory, fifth strong-MPN product.
- Per-row assertions: identity/Part Number preserved, seller SKU default, no cross-product media/price, audit terminal event; video may be `NO_RESULT`.

- [ ] **Step 1: Select five generic identities from existing fixtures/examples or stable live sources; no JBL-specific code paths.**
- [ ] **Step 2: Add deterministic fixture tests for identity/output/audit across all five categories.**
- [ ] **Step 3: Run a bounded live matrix for media/price where external sources permit and record external gaps separately.**
- [ ] **Step 4: Confirm no false attribution/cross-product result.**
- [ ] **Step 5: Commit** `test: certify generic multi-product workflows`.

### Task 6: Integration gates and Windows release

**Files:**
- Update workflows only if needed to make gates explicit.

- [ ] **Step 1: Run full pytest regression and require zero failures.**
- [ ] **Step 2: Run Price Intelligence live smoke and require PASS.**
- [ ] **Step 3: Run Media Integration live smoke and require valid image/video evidence or explicitly valid `NO_RESULT` without cross-product.**
- [ ] **Step 4: Run modern desktop smoke on Windows and require PASS.**
- [ ] **Step 5: Merge only after PR CI/live gates pass.**
- [ ] **Step 6: Build Windows with PyInstaller from merged `main`; require executable existence check PASS.**
- [ ] **Step 7: Verify uploaded `ProductIntelligence-Windows` artifact head SHA equals merged `main` SHA.**
- [ ] **Step 8: Report artifact ID, SHA-256 digest, and exact gate outcomes.**
