# PDF Review & Discovery V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PDF discovery precision-first and provenance-aware, then turn Revisión PDF into a true multi-page pre-approval workflow with OCR only after approval.

**Architecture:** Extend the existing discovery/review modules rather than replacing the working PDF pipeline. Add candidate identity/provenance metadata and strict pre-fetch filtering in `document_discovery.py`, multi-page on-demand rendering in `pdf_review.py`, reader controls and reviewed/automatic mode UI in `pdf_review_shell.py`, while keeping `pdf_review_batch.py` as the enforcement boundary.

**Tech Stack:** Python 3.12, PyMuPDF, Pillow/Tkinter, pytest, existing discovery/search/PDF/OCR/evidence modules.

## Global Constraints
- No product-specific hacks.
- Preserve Web/HTML, Multimedia, Price Intelligence, OCR.space, Mistral, updater, social video downloader and automatic PDF mode.
- Strong identity conflicts remain hard rejects.
- Review score never overrides identity gates.
- Reviewed mode: only approved PDFs can feed evidence; confirmed empty set means no PDF.
- Preview must not invoke OCR or Mistral.
- OCR happens after approval and must revalidate identity.

---

### Task 1: Precision candidate identity and query ladder

**Files:**
- Modify: `src/product_intelligence/document_discovery.py`
- Test: `tests/test_document_discovery_precision_v2.py`

**Interfaces:**
- Produces `DocumentCandidateAssessment` with `accepted`, `reason`, `identity_score`, `exact_strong_id`, `exact_model`, `conflict`.
- Produces `build_document_query_tiers(identity, official_domain=None) -> list[list[str]]`.

- [ ] Write RED tests proving sibling models and brand-only candidates are rejected before landing inspection/download, exact MPN ranks first, and queries are grouped into strict tiers.
- [ ] Run `python -m pytest tests/test_document_discovery_precision_v2.py -q` and confirm RED.
- [ ] Implement candidate assessment from URL/title/snippet/domain using strong identifiers first, then exact brand+model; conflicting strong identifiers or sibling models hard reject.
- [ ] Replace the flat 12-query prefix with tiered escalation and quality-based early stop while preserving `build_document_queries()` compatibility for existing callers.
- [ ] Run focused tests and commit.

### Task 2: Dedupe, exact-PDP pivot and provenance

**Files:**
- Modify: `src/product_intelligence/document_discovery.py`
- Test: `tests/test_document_provenance_v2.py`

**Interfaces:**
- Add `DocumentProvenance(parent_url, parent_identity_status, parent_identity_confidence, parent_authority, anchor_text, discovery_method)`.
- Extend resolved document candidates with provenance metadata without breaking existing `SearchCandidate` consumers.

- [ ] Write RED tests proving duplicate landings are inspected once, exact PDP stops broad search and pivots to linked documents, and linked PDF preserves parent provenance.
- [ ] Write RED test proving a linked PDF with missing internal MPN can be provenance-bound while a PDF containing a conflicting strong identifier is still rejected.
- [ ] Implement canonical URL dedupe, exact-PDP detection/pivot, and provenance propagation.
- [ ] Add trace events for pre-fetch rejection, duplicate, exact PDP, pivot, and provenance-bound document.
- [ ] Run focused tests and commit.

### Task 3: Review candidate model and remote-first discovery

**Files:**
- Modify: `src/product_intelligence/pdf_review.py`
- Test: `tests/test_pdf_review_v2.py`

**Interfaces:**
- Extend `PdfReviewCandidate` with provenance, authority, identity status/reason and preliminary score.
- Discovery returns filtered/ranked metadata candidates without downloading their PDFs.
- Add `render_pdf_page(local_path, page_index, zoom) -> bytes`.

- [ ] Write RED tests proving discovery itself does not call `download_pdf`, wrong-model candidates never surface, provenance-bound candidates expose the state, and page rendering works for arbitrary page indexes.
- [ ] Run focused tests and confirm RED.
- [ ] Implement metadata-only discovery and transparent review score: identity 40, authority 20, provenance 15, document type 10, text quality 10, discovery relevance 5; hard conflicts remain reject.
- [ ] Replace first-page-only rendering with on-demand page rendering while keeping a compatibility first-page preview property where needed.
- [ ] Run focused tests and commit.

### Task 4: Multi-page PDF reader UI

**Files:**
- Modify: `src/product_intelligence/pdf_review_shell.py`
- Test: `tests/test_pdf_review_reader_contract.py`

**Interfaces:**
- UI state: current page, zoom, fit mode, rendered-page cache per inspected document.
- Actions: first/previous/next/last, zoom in/out, fit width, fit page.

- [ ] Write RED source/behavior contracts requiring Page X/N, first/prev/next/last, horizontal+vertical scroll, zoom 50–200%, fit width/page, wheel scroll and Ctrl+wheel zoom.
- [ ] Run focused tests and confirm RED.
- [ ] Replace the preview label with a scrollable canvas and render the current page on demand.
- [ ] Cache rendered pages by `(url, page_index, zoom/fit)`; never rasterize the entire document upfront.
- [ ] Keep preview inspection OCR/Mistral-free.
- [ ] Run focused tests and commit.

### Task 5: Reviewed vs automatic PDF mode and strict approval contract

**Files:**
- Modify: `src/product_intelligence/pdf_review_shell.py`
- Modify if required: `src/product_intelligence/pdf_review_batch.py`
- Test: `tests/test_pdf_review_mode_v2.py`

**Interfaces:**
- Mode values: `reviewed` and `automatic`.
- Reviewed mode stops after candidate search until explicit confirmation.

- [ ] Write RED tests proving reviewed mode never auto-ingests discovered PDFs, only confirmed URLs feed batch evidence, and confirmed empty set disables PDF for that product.
- [ ] Keep automatic mode behavior compatible with legacy execution.
- [ ] Add visible mode control with reviewed mode selected by default inside the review workflow.
- [ ] Prevent rejected/conflict candidates from being approved.
- [ ] Run focused tests and commit.

### Task 6: OCR-after-approval and page-selective quality routing

**Files:**
- Modify minimal existing PDF/OCR routing owner discovered during audit; do not duplicate OCR clients.
- Test: `tests/test_pdf_review_ocr_routing_v2.py`

**Interfaces:**
- Add a pure page-quality assessment helper returning `native_ok`, `ocr_required`, and a reason.
- OCR input in reviewed mode is restricted to approved PDFs and selected low-quality/spec-relevant pages.

- [ ] Write RED tests proving preview never calls OCR, unapproved PDFs never call OCR, approved low-quality pages can call OCR, and post-OCR identity conflict still rejects.
- [ ] Implement page-quality heuristic using chars/page, printable/alphanumeric ratios, garbage repetition/image dominance and technical-keyword usefulness, reusing current OCR.space/fallback clients.
- [ ] Re-run identity validation after OCR before evidence admission.
- [ ] Run focused tests and commit.

### Task 7: Page-level evidence trace

**Files:**
- Modify minimal existing evidence-record owner(s) only where required.
- Test: `tests/test_pdf_page_evidence_trace_v2.py`

**Interfaces:**
- Evidence carries document URL, parent landing, page number, extraction method, raw snippet, canonical field, normalized value and confidence.

- [ ] Write RED tests for page/provenance trace preservation through accepted evidence.
- [ ] Implement additive trace metadata without weakening current evidence gates or Excel mapping.
- [ ] Run focused tests and commit.

### Task 8: Benchmark and regression gates

**Files:**
- Create: `scripts/pdf_review_discovery_v2_benchmark.py`
- Test/update only benchmark contract tests as needed.

**Interfaces:**
- Benchmark identities: JBLQ350WLBLKAM, JBLENDURRUN3BTBAM, JBLT530CBLKAM; QA fixtures only, never production hardcoding.
- Report: queries, raw results, deduped candidates, wrong-model rejects, generic rejects, exact PDPs, landings, PDFs downloaded before review, relevant PDFs surfaced, validated PDFs, elapsed time.

- [ ] Run full `python -m pytest -q`.
- [ ] Run benchmark and require wrong-model downloaded = 0, cross-product contamination = 0, invented specs = 0; compare search noise and useful candidates against the captured baseline.
- [ ] Run existing desktop/provider, Multimedia, Price Intelligence, social-video, updater and packaging contract suites/workflows.
- [ ] Fix only regressions caused by this feature.

### Task 9: Version, PR and Windows release

**Files:**
- Modify: `src/product_intelligence/version.py`
- Modify: `pyproject.toml`
- Modify version expectation tests.

- [ ] Bump one patch version only after all prior gates are green.
- [ ] Run final CI on the exact head.
- [ ] Open PR to `release/windows`; inspect changed-file set for scope control.
- [ ] Merge only with green exact-head gates.
- [ ] Verify Release Windows builds EXE/updater, resources, ZIP/SHA and publishes an immutable new tag.
- [ ] Report exact commit, run IDs, release tag, benchmark metrics and PASS/FAIL gates.