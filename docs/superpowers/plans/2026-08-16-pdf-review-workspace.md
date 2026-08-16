# PDF Review Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a PDF review workspace that lets the user inspect, preview and explicitly approve technical PDFs before those PDFs can contribute evidence to the Excel scraping run.

**Architecture:** Add a Tk-free review service for discovery/inspection/preview, then wire a dedicated workspace into `pdf_desktop.App`. Extend the batch contract with per-product reviewed PDF URLs and an enforcement flag so confirmed products use only approved PDFs while existing Web/HTML acquisition remains unchanged.

**Tech Stack:** Python 3.12, PyMuPDF, Pillow/Tkinter, pytest, existing document discovery and PDF identity validation.

## Global Constraints
- Review is optional per product; unreviewed products retain current automatic PDF behavior.
- A confirmed review disables only automatic PDF following/discovery for that product; Web/HTML continues normally.
- Review preview never invokes OCR or Mistral.
- OCR remains a fallback in the existing extraction path when native PDF text is insufficient and OCR is enabled.
- Mistral remains downstream of validated canonical facts.
- Identity/evidence gates are never weakened.
- Price Intelligence and Multimedia remain unchanged.

---

### Task 1: PDF review service

**Files:**
- Create: `src/product_intelligence/pdf_review.py`
- Create: `tests/test_pdf_review.py`

**Interfaces:**
- Produces: `PdfReviewCandidate`, `PdfInspection`, `discover_review_candidates(identity, limit=8)`, `inspect_pdf_candidate(identity, url, cache_dir)`, `score_review_candidate(...)`.

- [ ] Write failing tests that generate a small PDF with PyMuPDF and assert document classification, identity acceptance, page count, native text count, OCR recommendation and PNG preview bytes.
- [ ] Run `python -m pytest tests/test_pdf_review.py -q` and confirm RED because the module/API does not exist.
- [ ] Implement discovery by wrapping `discover_product_documents` and inspection by using `pdf_download.download_pdf`, PyMuPDF native text extraction, `validate_pdf_identity`, and first-page PNG rendering.
- [ ] Ensure inspection never imports/calls OCR or Mistral providers.
- [ ] Re-run focused tests and confirm GREEN.

### Task 2: Reviewed-PDF batch enforcement

**Files:**
- Modify: `src/product_intelligence/batch.py`
- Create: `tests/test_pdf_review_batch_contract.py`

**Interfaces:**
- `BatchItem` gains `reviewed_pdf_urls: list[str] | None` and `pdf_review_enforced: bool`.
- `manual_identity_items(..., reviewed_pdf_urls_by_index=None, pdf_review_flags=None)` forwards per-product review state.
- `run_batch(..., reviewed_pdf_urls_by_index=None, pdf_review_flags=None)` forwards it to `BatchItem`.

- [ ] Write failing tests proving a confirmed review inserts approved PDF URLs, sets `include_pdfs=False` for HTML pipeline calls, skips `_ingest_direct_documents`, and keeps Web candidates available.
- [ ] Run `python -m pytest tests/test_pdf_review_batch_contract.py -q` and confirm RED.
- [ ] Implement the minimal batch changes. Approved PDFs become explicit PDF candidates. For enforced products, automatic PDFs from HTML, direct PDF fallback, and PDF gap discovery are skipped.
- [ ] Preserve current behavior when `pdf_review_enforced=False`.
- [ ] Re-run focused tests and confirm GREEN.

### Task 3: Desktop review workspace

**Files:**
- Modify: `src/product_intelligence/pdf_desktop.py`
- Create: `tests/test_pdf_review_desktop_contract.py`

**Interfaces:**
- App state: `_pdf_review_candidates`, `_pdf_review_selected`, `_pdf_review_enforced`, `_pdf_review_photo`.
- New workspace key: `pdf_review`.
- New actions: `_pdf_review_search`, `_pdf_review_inspect_selected`, `_pdf_review_toggle_use`, `_pdf_review_confirm`, `_pdf_review_refresh_tree`.

- [ ] Write failing source-contract tests requiring a `Revisión PDF` workspace, candidate Treeview, preview panel, `Buscar PDFs`, `Usar / quitar`, `Confirmar selección`, and forwarding of `reviewed_pdf_urls_by_index`/`pdf_review_flags` to `run_batch`.
- [ ] Run `python -m pytest tests/test_pdf_review_desktop_contract.py -q` and confirm RED.
- [ ] Add the workspace and sidebar button after existing parent initialization.
- [ ] Use a product Combobox tied to existing `_identity_for_index`/`product_rows`.
- [ ] Run discovery and inspection in daemon threads; use `after()` for Tk updates.
- [ ] Render preview PNG with Pillow `ImageTk.PhotoImage` and keep a strong reference in `_pdf_review_photo`.
- [ ] Prevent identity-rejected candidates from being toggled into the approved set.
- [ ] Confirming selection marks that product as enforced, including an intentionally empty selected set.
- [ ] Snapshot the review maps before starting Excel and pass them through `ExecutionSnapshot.options` into `run_batch`.
- [ ] Re-run focused tests and confirm GREEN.

### Task 4: Packaging/version/regression

**Files:**
- Modify only if required by packaging/version contracts: `ProductIntelligence.spec`, `pyproject.toml`, `src/product_intelligence/version.py`, version expectation tests.

- [ ] Run `python -m pytest -q` and fix only regressions caused by this feature.
- [ ] Verify PyMuPDF/Pillow are already runtime dependencies; avoid adding new packages if possible.
- [ ] Bump the application to the next patch version only after the feature branch is fully green.
- [ ] Run full CI and existing media/price relevant workflow gates.
- [ ] Review PR diff to confirm no Price Intelligence, social downloader, OCR provider or Mistral provider behavior was changed.
- [ ] Merge to `release/windows` only after the exact final head is green.
