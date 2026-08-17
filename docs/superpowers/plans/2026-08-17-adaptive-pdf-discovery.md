# Adaptive PDF Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace only the PDF discovery engine with a bounded adaptive identity-first pipeline that resolves product identity, prioritizes manufacturer documentation, validates real PDFs and provenance, and feeds the existing PDF Review UI without changing WEB, OCR/Mistral, Excel, pricing, multimedia, Mercado Libre, or other independent behavior.

**Architecture:** Keep the v0.10.30 production shell and PDF Review contract. Introduce one shared PDF-discovery orchestration path: normalize identifier → direct precision search → identity bootstrap/refinement → canonical product identity → manufacturer/PDP/support search → trusted bridge fallback → targeted document search → browser fallback only when justified → real-PDF validation → identity/provenance scoring → dedupe/rank → bounded early stop → PDF Review. Reuse existing discovery/search/download primitives where safe; do not port PR #57 wholesale.

**Tech Stack:** Python 3, requests, existing browser_search/Playwright fallback, PyMuPDF, pytest, GitHub Actions Windows smoke.

## Global Constraints

- PDF mode only; WEB mode remains unchanged.
- Discovery may use the web only to locate/confirm PDFs; HTML is not evidence for filling Excel in PDF mode.
- OCR/Mistral must remain zero during PDF discovery and run only after explicit selection under existing reviewed-mode semantics.
- No product/brand/URL hardcoding; JBL identifiers are QA fixtures only.
- Search must be bounded and adaptive; no brute-force crawl/download-first strategy.
- A valid user decision of 0 PDFs selected remains distinct from an unreviewed product.
- Do not claim 3/3 until real smoke evidence proves it.
- Preserve v0.10.30 Multimedia, Mercado Libre, updater, final desktop shell, and release gates.

---

### Task 1: Map and freeze the production PDF path

**Files:**
- Read: `src/product_intelligence/pdf_review_shell.py`
- Read: `src/product_intelligence/pdf_review.py`
- Read: `src/product_intelligence/document_discovery.py`
- Read: `src/product_intelligence/pdf_review_batch.py`
- Read: `src/product_intelligence/document_ingestion.py`
- Read: `src/product_intelligence/pdf_download.py`
- Read: `src/product_intelligence/discovery.py`
- Test: `tests/test_pdf_production_path_contract.py`

**Interfaces:**
- Consumes: current `discover_review_candidates(identity, limit)` and reviewed allow-list contract.
- Produces: regression guard proving final desktop review uses the same shared discovery entry point and that OCR/Mistral are not called by discovery.

- [ ] Write failing contract tests for the final `.exe` route and zero provider calls during discovery.
- [ ] Run focused tests and record RED evidence.
- [ ] Make only integration changes needed to route all reviewed discovery through one shared entry point.
- [ ] Run focused tests to GREEN.
- [ ] Commit.

### Task 2: Product identity model and normalization for PDF discovery

**Files:**
- Create: `src/product_intelligence/pdf_identity.py`
- Modify: `src/product_intelligence/models.py` only if a compatible additive type is required.
- Test: `tests/test_pdf_identity_resolution.py`

**Interfaces:**
- Produces: `PdfProductIdentity` / resolved identity containing original identifier, normalized identifier/type, brand, manufacturer, canonical model, commercial name, family, variant attributes, manufacturer domain, aliases, source chain, confidence.

- [ ] Write RED tests for MPN-only, EAN/UPC/GTIN normalization, meaningful hyphen preservation, and base-model vs variant separation.
- [ ] Implement minimal normalization and identity object.
- [ ] Run focused tests GREEN.
- [ ] Commit.

### Task 3: Adaptive identity resolution using shared search evidence

**Files:**
- Create: `src/product_intelligence/pdf_identity_resolver.py`
- Reuse: `src/product_intelligence/discovery.py`
- Reuse: `src/product_intelligence/browser_search.py`
- Test: `tests/test_pdf_identity_adaptive_search.py`

**Interfaces:**
- Consumes: identifier + existing search providers.
- Produces: resolved identity plus bounded search metrics and identity source URLs.

- [ ] Write RED tests: exact identifier result resolves brand/model; snippet-bound evidence requires corroboration; retailer hostname cannot become brand; multiple independent sources can corroborate canonical model; unresolved identity yields `IDENTITY_UNRESOLVED`.
- [ ] Implement precision-first direct search followed by bounded identity queries; share the same result pool with document discovery instead of separate blind search engines.
- [ ] Add confidence/consensus rules that are manufacturer-agnostic.
- [ ] Run GREEN and regression.
- [ ] Commit.

### Task 4: Canonical aliases and bounded document-query planner

**Files:**
- Create: `src/product_intelligence/pdf_query_planner.py`
- Test: `tests/test_pdf_query_planner.py`

**Interfaces:**
- Consumes: resolved identity.
- Produces: ordered query tiers with explicit category and budget.

- [ ] RED tests for direct identifier, official-domain, canonical model/specsheet/manual/QSG, language variants, no absurd aliases, and explicit bounded budgets.
- [ ] Implement adaptive planner that emits next queries based on learned identity/source state instead of generating all combinations up front.
- [ ] GREEN + commit.

### Task 5: Manufacturer-first PDP/support/document discovery

**Files:**
- Create: `src/product_intelligence/pdf_discovery_engine.py`
- Refactor narrowly: `src/product_intelligence/document_discovery.py`
- Reuse: `src/product_intelligence/browser_search.py`
- Test: `tests/test_pdf_pdp_support_pivot.py`

**Interfaces:**
- Consumes: resolved identity + query planner.
- Produces: document leads with source context/provenance before download.

- [ ] RED tests for official exact PDP, PDP → support → downloads → PDF, embedded JSON/JSON-LD/data-attribute document URLs, official regional domains, trusted retailer bridge to manufacturer PDF, and browser fallback only after static evidence indicates it is needed.
- [ ] Implement bounded static inspection and one justified browser fallback.
- [ ] Preserve source chain on every lead.
- [ ] GREEN + commit.

### Task 6: Real PDF validation and pre-candidate garbage rejection

**Files:**
- Create: `src/product_intelligence/pdf_candidate_validation.py`
- Reuse: `src/product_intelligence/pdf_download.py`
- Reuse/refactor: `src/product_intelligence/pdf_evidence.py`
- Test: `tests/test_pdf_candidate_validation.py`

**Interfaces:**
- Consumes: document leads.
- Produces: validated PDF candidates with final URL, MIME/magic/file size/SHA256/parser validity.

- [ ] RED tests: `.pdf` tracking/social URL rejected before candidate; HTML disguised as PDF rejected; `%PDF-`/parser validation required; valid official CDN not blocked merely because hostname differs from main brand domain.
- [ ] Implement validation and safe rejection reasons.
- [ ] GREEN + commit.

### Task 7: Identity binding, provenance, confidence, dedupe and ranking

**Files:**
- Create: `src/product_intelligence/pdf_provenance.py`
- Modify narrowly: `src/product_intelligence/pdf_review.py`
- Test: `tests/test_pdf_provenance_and_ranking.py`

**Interfaces:**
- Produces: candidate fields for relation type, identity confidence, document confidence, provenance_bound, authority, document type/language, canonical/final URL and SHA256.

- [ ] RED tests for canonical-model acceptance when MPN is absent from PDF filename/content but trusted provenance binds it; wrong sibling model rejection; trusted bridge provenance preservation; tracking-query duplicate collapse; SHA256 final dedupe; Spanish preference only among equivalent-authority/equivalent-quality docs.
- [ ] Implement HIGH/MEDIUM/LOW/REJECT scoring and ranking.
- [ ] GREEN + commit.

### Task 8: Bounded orchestration, statuses, metrics and early stop

**Files:**
- Modify: `src/product_intelligence/pdf_discovery_engine.py`
- Modify: `src/product_intelligence/document_discovery.py` compatibility wrapper.
- Test: `tests/test_pdf_discovery_budget_and_status.py`

**Interfaces:**
- Produces statuses `PDF_FOUND`, `NO_VALIDATED_PDF_FOUND`, `IDENTITY_UNRESOLVED`, `SEARCH_PARTIAL`, `NETWORK_ERROR`, `PARSER_ERROR`; metrics for queries/results/landings/PDP/support/pivots/raw links/filtered links/candidates/provenance/downloads/duplicates/official PDFs/browser fallback/stop reason.

- [ ] RED tests for bounded budgets, no 100+ direct-identifier loop, early stop after sufficient high-confidence document classes, and correct no-result vs error semantics.
- [ ] Implement orchestration and concise operational logs `[PDF][IDENTITY]`, `[PDF][DOC_SEARCH]`, `[PDF][PDP]`, `[PDF][PDF_FOUND]`, `[PDF][VALIDATION]`, `[PDF][STOP]`.
- [ ] GREEN + commit.

### Task 9: Preserve PDF Review semantics and real `.exe` integration

**Files:**
- Modify narrowly: `src/product_intelligence/pdf_review.py`
- Modify narrowly: `src/product_intelligence/pdf_review_shell.py` only for additive candidate fields/statuses.
- Test: `tests/test_pdf_review_adaptive_engine_integration.py`

**Interfaces:**
- Existing selection/confirmation/allow-list behavior remains unchanged.

- [ ] RED tests that discovery returns candidates without OCR/Mistral, only selected URLs reach `process_pdf_document`, zero-selection is valid, unreviewed product remains blocked in reviewed mode.
- [ ] Wire engine output to current Review view.
- [ ] GREEN + commit.

### Task 10: Real smoke before/after — JBL 3/3

**Files:**
- Create/replace: `scripts/adaptive_pdf_discovery_benchmark.py`
- Workflow: `.github/workflows/adaptive-pdf-discovery-smoke.yml`

- [ ] Capture baseline from v0.10.30 for `JBLQ350WLBLKAM`, `JBLENDURRUN3BTBAM`, `JBLT530CBLKAM`.
- [ ] Run new engine with structured metrics.
- [ ] Require identity 3/3, validated PDF 3/3, false tracking/social candidate 0, provenance on accepted HIGH documents where demonstrable.
- [ ] Do not change production rules to make these fixtures pass.
- [ ] Commit only after reproducible evidence.

### Task 11: Multi-brand/category generalization

**Files:**
- Extend: `scripts/adaptive_pdf_discovery_benchmark.py`
- Test/workflow fixture configuration only; no production hardcodes.

- [ ] Test diverse available products across laptop, smartphone, headphone, mouse, monitor, cable/accessory, printer/other with multiple brands.
- [ ] Record identity, documents, domains, confidence and request budgets.
- [ ] Fix only general failure classes; rerun JBL regression after every general fix.
- [ ] Commit.

### Task 12: Final regression and Windows certification

**Files:**
- Update workflow only if required to add the new PDF gate; do not weaken existing v0.10.30 gates.

- [ ] Run full pytest regression.
- [ ] Run final desktop shell smoke using `final_live_ui_desktop.App`.
- [ ] Run adaptive PDF real smoke.
- [ ] Verify WEB mode unchanged, OCR/Mistral unchanged during discovery, Excel unchanged, PDF Review working, Multimedia/ML existing gates unchanged.
- [ ] Produce final root-cause, before/after architecture, files changed, RED→GREEN tests, smoke table, JBL results, multimarca evidence, request budget and regression report.
