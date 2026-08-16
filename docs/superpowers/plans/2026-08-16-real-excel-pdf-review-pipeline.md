# Real Excel PDF Review Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the real Excel/Windows EXE flow implement identity-first PDF discovery, download/validation before review, explicit review state, and exact selected-PDF handoff without invoking OCR/Mistral during discovery.

**Architecture:** Reuse the existing identity bootstrap, document discovery, downloader, identity validator, review UI, batch pipeline, OCR and Mistral. Move identity enrichment into the real document-discovery boundary, add one shared review discovery/validation service that produces validated downloaded candidates, feed those candidates into the existing Review PDF UI, and make the review plan carry exact selected cached documents into the existing PDF ingestion path. Automatic PDF mode continues to use the same identity resolver, document discovery and PDF validator.

**Tech Stack:** Python 3.12, Tkinter, requests, PyMuPDF, Pydantic, pytest, PyInstaller.

## Global Constraints

- Work on `fix/excel-reviewed-pdf-bootstrap`, never `main`.
- Real Excel/EXE path only; no parallel demo implementation.
- `DISCOVERED != SELECTED != PROCESSED`.
- Discovery/validation must not call OCR or Mistral.
- `WEB=OFF, PDF=ON` may still use HTML/search for discovery but HTML cannot become final specification evidence.
- Review required + not confirmed must block execution and never fall back to automatic PDF.
- Confirmed zero PDFs is a valid decision.
- Keep existing OCR, Mistral, Excel mapping and extraction behavior unchanged except for strict handoff wiring.
- Precision > coverage; wrong-product PDFs remain rejected.

---

### Task 1: Native identity-first document discovery

**Files:**
- Modify: `src/product_intelligence/document_discovery.py`
- Test: `tests/test_pdf_review_real_pipeline.py`

**Interfaces:**
- Produces: `prepare_document_identity(identity, timeout=8) -> tuple[ProductIdentity, str | None]`
- `discover_product_documents()` calls it internally before query planning.

- [ ] Add RED tests proving MPN-only input is bootstrapped before query generation.
- [ ] Move/reuse existing identity bootstrap at the document discovery boundary.
- [ ] Preserve strong identifiers from Excel when bootstrap enriches brand/model.
- [ ] Run focused tests.

### Task 2: Shared download + validation service for review

**Files:**
- Create: `src/product_intelligence/pdf_review_service.py`
- Modify: `src/product_intelligence/pdf_review.py`
- Test: `tests/test_pdf_review_real_pipeline.py`

**Interfaces:**
- Produces: `ValidatedPdfCandidate`
- Produces: `discover_validated_review_pdfs(identity, cache_dir, limit=8, timeout=...)`

- [ ] RED test: discovery candidates are downloaded and structurally validated before surfacing.
- [ ] RED test: wrong-product PDF is excluded.
- [ ] RED test: duplicate final URL/hash is shown once.
- [ ] Implement service using existing `discover_product_documents`, `download_pdf`, PyMuPDF and `validate_pdf_identity`/provenance.
- [ ] Ensure no OCR/Mistral imports or calls.

### Task 3: Feed validated candidates into existing Review PDF UI

**Files:**
- Modify: `src/product_intelligence/pdf_review_shell.py`
- Test: `tests/test_pdf_review_real_pipeline.py`

**Interfaces:**
- UI search receives validated downloaded candidates and pre-populated `PdfInspection` objects.

- [ ] RED test: search path uses shared validated service.
- [ ] Replace metadata-only search + click-time download with background download/validation during `Buscar PDFs`.
- [ ] Show only validated/selectable candidates; preserve multipage preview/zoom.
- [ ] Preserve explicit confirmation including zero PDFs.

### Task 4: Exact selected-document handoff

**Files:**
- Modify: `src/product_intelligence/pdf_review_batch.py`
- Modify: `src/product_intelligence/document_ingestion.py`
- Test: `tests/test_pdf_review_real_pipeline.py`

**Interfaces:**
- Review plan carries selected URLs and their validated local paths/provenance.
- `process_pdf_document(..., local_path=None)` can reuse already validated/downloaded bytes.

- [ ] RED test: four validated, two selected -> exactly two PDF ingestions.
- [ ] RED test: zero selected -> zero PDF ingestions and no automatic rediscovery.
- [ ] RED test: unreviewed -> blocked before batch handoff.
- [ ] Implement local cached-document reuse without changing extraction/OCR semantics.

### Task 5: Remove runtime monkey-patch as source of truth

**Files:**
- Modify/Delete: `src/product_intelligence/excel_pdf_review_hardening.py`
- Modify: `run_desktop.py`
- Test: existing launcher/desktop contracts + `tests/test_pdf_review_real_pipeline.py`

- [ ] Replace runtime adapter wiring with direct imports/native behavior.
- [ ] Keep launcher compatibility (`managed_main()`).
- [ ] Verify Review and Automatic share the native resolver/discovery/validator.

### Task 6: Real-flow QA gates

**Files:**
- Modify: `scripts/pdf_review_discovery_v2_benchmark.py`
- Test: full suite + live workflow

- [ ] Benchmark uses MPN-only inputs exactly like Excel.
- [ ] Report resolved brand/model/domain and validated downloaded candidate counts.
- [ ] Do not call OCR/Mistral before review confirmation.
- [ ] Keep query/landing/download budgets and precision gates.
- [ ] Run full regression, PDF review live benchmark and Windows build before version bump/release.
