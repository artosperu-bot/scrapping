# PDP-First Reviewed PDF Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Revisión PDF reliably resolve an exact official product page from MPN/EAN/UPC/GTIN, extract/download product documents from that validated parent page before generic PDF search, and preserve user-controlled OCR/Mistral execution only after PDF selection.

**Architecture:** Add an official-PDP-first pass in the reviewed-PDF discovery strategy using the existing identity resolver, candidate assessment, landing inspection, provenance binding, downloader and validator. Keep the current `filetype:pdf` query ladder and browser/general search as fallback. Reuse the existing reviewed allow-list so only selected PDFs enter `process_pdf_document`; expose post-selection extraction/provider stages in Revisión PDF without moving OCR/Mistral into discovery.

**Tech Stack:** Python 3.10+, requests, Playwright fallback, PyMuPDF, Tkinter/ttk, existing OCR.space/Mistral provider runtime, pytest, GitHub Actions, PyInstaller.

## Global Constraints
- Production logic must remain product/brand agnostic; JBL part numbers are QA fixtures only.
- Identifier priority remains MPN → EAN → UPC → GTIN.
- Discovery must perform zero OCR and zero Mistral calls.
- Exact official PDP provenance may bind a linked PDF even when the PDF filename does not contain the identifier, but only after the parent PDP is exact/strong and manufacturer-owned.
- Search-first PDF discovery remains fallback, not removed.
- Reviewed mode must never process an unselected PDF and an explicit selection of zero PDFs remains valid.
- Existing OCR.space behavior remains PyMuPDF/native-text first and OCR fallback only when configured and needed.
- Existing Mistral responsibilities remain grounded and provider-configured; do not invent PDF facts or bypass evidence gates.
- Revisión PDF must visibly distinguish discovery/download/validation from post-selection extraction/OCR/Mistral stages.
- Full regression, live three-product PDF smoke and Windows release gates must pass before release.

---

### Task 1: Contract for exact official PDP pivot

**Files:**
- Modify: `tests/test_pdf_review_discovery_v2.py`
- Modify: `tests/test_pdf_query_budget_contract.py` only if needed for the new pre-pass accounting
- Modify: `src/product_intelligence/pdf_review_search_strategy.py`

**Interfaces:**
- Consumes: `ProductIdentity`, `core._strong_identifiers`, `core._clean_official_domain`, `core.search_web_query_candidates`, `core._accept_search_candidate`, `core._resolve_valid_candidates`.
- Produces: `_discover_official_pdp_documents(identity, official_domain, limit, timeout, trace) -> list[SearchCandidate]`.

- [ ] **Step 1: Write failing tests** proving that an exact official PDP returned by `site:official-domain "IDENTIFIER"` is inspected before `filetype:pdf` queries, and that a linked spec sheet whose filename omits the MPN is returned with manufacturer provenance.
- [ ] **Step 2: Run focused tests** with `python -m pytest -q tests/test_pdf_review_discovery_v2.py tests/test_pdf_query_budget_contract.py` and confirm RED for missing PDP-first behavior.
- [ ] **Step 3: Implement the minimal PDP-first pass**. Search only the validated official domain with strong identifiers, accept only exact/strong non-PDF product landings, immediately call the existing landing resolver, and return only resolved PDF candidates.
- [ ] **Step 4: Preserve fallback** by calling the existing priority query tiers only when the PDP-first pass returns no usable documents.
- [ ] **Step 5: Re-run focused tests** and confirm GREEN.

### Task 2: Live observability for the real PDF boundary

**Files:**
- Modify: `src/product_intelligence/live_pdf_discovery.py`
- Modify: `src/product_intelligence/pdf_review_search_strategy.py`
- Modify: `tests/test_pdf_live_ui_contract.py`

**Interfaces:**
- Produces trace/live events for `PDP_SEARCH`, `PDP_VALIDATED`, `DOCUMENT_FOUND`, existing `DOWNLOAD`, `VALIDATE`, `DONE`.

- [ ] **Step 1: Write failing tests** that a successful PDP pivot generates observable parent-PDP and document discovery evidence before download events.
- [ ] **Step 2: Confirm RED** on the focused live UI test.
- [ ] **Step 3: Bridge existing trace events into the review live callback** without changing Tk from worker threads.
- [ ] **Step 4: Confirm GREEN** and verify `DONE` includes discovered/downloaded/validated/rejected/duplicates counts.

### Task 3: Post-selection OCR/Mistral contract inside Revisión PDF

**Files:**
- Modify: `tests/test_pdf_review_batch_contract.py`
- Modify: `tests/test_provider_pdf_runtime.py`
- Modify: `src/product_intelligence/pdf_review_batch.py` only if a gap is demonstrated
- Modify: `src/product_intelligence/pdf_review_shell.py` or final review shell only for stage/status rendering

**Interfaces:**
- Consumes: `set_desktop_review_plan`, `scrape_item_with_review`, existing `process_pdf_document`, OCR provider runtime and Mistral/provider execution context.
- Produces: explicit post-selection status/events while preserving the same business pipeline.

- [ ] **Step 1: Write failing tests** proving discovery never invokes OCR/Mistral; after confirmation, only selected PDF URLs reach `process_pdf_document`; zero-selection triggers neither provider; unselected URLs are rejected.
- [ ] **Step 2: Audit current provider semantics**. Preserve PyMuPDF-first/OCR.space fallback and preserve Mistral's existing grounded role; do not relabel Mistral as OCR.
- [ ] **Step 3: If current execution is already correct, add only UI/audit event wiring** for `TEXT_EXTRACT`, `OCR`, and `MISTRAL` when those stages truly run. If a functional gap exists, make the smallest fix at the selected-PDF boundary.
- [ ] **Step 4: Run provider/PDF review tests** and confirm no plaintext credentials or invented provider calls.

### Task 4: Strengthen the real three-product smoke

**Files:**
- Modify: `scripts/pdf_review_discovery_v2_benchmark.py`
- Modify: `.github/workflows/pdf-review-discovery-v2-smoke.yml`

**Interfaces:**
- QA dataset only: `JBLQ350WLBLKAM`, `JBLENDURRUN3BTBAM`, `JBLT530CBLKAM`.

- [ ] **Step 1: Raise the live gate** to require for all 3 products: descriptive identity resolved, official domain present, at least one discovered PDF, at least one download attempt, and at least one validated/provenance-bound product PDF.
- [ ] **Step 2: Record provenance parent, final PDF URL, pages, SHA256 and diagnostic log** for every accepted PDF.
- [ ] **Step 3: Assert discovery contract reports `ocr_before_review=0` and `mistral_before_review=0`** and no cross-product contamination.
- [ ] **Step 4: Run the GitHub Actions smoke** with real internet/Chromium and require 3/3 PASS before merge.

### Task 5: Regression, version and Windows release

**Files:**
- Modify after all behavior gates pass: `src/product_intelligence/version.py`, `pyproject.toml`, version-specific test guards.

- [ ] **Step 1: Run full CI** and PDF Review V2 tests on the final functional head.
- [ ] **Step 2: Review diff** for product-specific production logic, accidental OCR/Mistral-before-review behavior, and source/identity gate weakening.
- [ ] **Step 3: Bump to `0.10.29` only after functional and live PDF smoke gates are green.**
- [ ] **Step 4: Re-run fresh CI/PDF smoke on the exact versioned head.**
- [ ] **Step 5: Merge to `release/windows` and require Release Windows to pass version verification, regression, shell smoke, Chromium, clean EXE build, updater bootstrap, ZIP, SHA256 and GitHub Release publication.**
