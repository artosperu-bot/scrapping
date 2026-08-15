# Selective Long-PDF Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Process long PDFs selectively so specification extraction stays useful and bounded.

**Architecture:** Keep the existing PDF evidence pipeline. Add a deterministic page selector in `pdf_extract.py`; short PDFs preserve current full extraction, while long PDFs scan native text cheaply and fully extract/OCR only selected pages. `document_ingestion.py` supplies model/identifier/target terms as focus signals.

**Tech Stack:** Python 3.12, PyMuPDF, pytest.

## Global Constraints
- No brand/product hardcodes.
- Do not change automatic identity discovery.
- <=10 pages: full processing.
- >10 pages: at most 15 fully processed pages; first 8 pages have baseline priority.
- OCR only selected pages.
- Existing fail-closed evidence policy remains authoritative.

---

### Task 1: Page-selection contract

**Files:**
- Create: `tests/test_pdf_selective_extraction.py`
- Modify: `src/product_intelligence/pdf_extract.py`

**Interfaces:**
- Produces: `select_pdf_page_indexes(page_texts, focus_terms=None, short_limit=10, head_pages=8, max_pages=15) -> list[int]`

- [ ] Write tests proving short PDFs select every page and long PDFs cap selection while retaining a late exact-model/specification page.
- [ ] Run the tests and confirm RED because the selector does not exist yet.
- [ ] Implement the minimal deterministic selector.
- [ ] Run the focused tests and confirm GREEN.

### Task 2: Selective extraction integration

**Files:**
- Modify: `src/product_intelligence/pdf_extract.py`
- Modify: `src/product_intelligence/document_ingestion.py`
- Test: `tests/test_pdf_selective_extraction.py`

**Interfaces:**
- `extract_pdf_bytes(..., focus_terms=None)` and `extract_pdf(..., focus_terms=None)` preserve backward compatibility.

- [ ] Add a generated long-PDF test proving unselected blank pages do not trigger OCR and selected late model/spec pages remain available.
- [ ] Confirm RED under current full-document behavior.
- [ ] Make long-PDF extraction use the selector and OCR only selected pages.
- [ ] Pass identity model/product name/MPN/EAN/UPC/GTIN and requested target semantics from document ingestion.
- [ ] Run focused PDF tests, CI, PDF smoke and Source Validation.
