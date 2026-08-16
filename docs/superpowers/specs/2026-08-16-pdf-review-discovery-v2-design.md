# PDF Review & Discovery V2 Design

## Goal
Build a precision-first, human-in-the-loop PDF workflow that surfaces only product-relevant documents, preserves landing→PDF provenance, lets the user inspect multi-page PDFs before approval, and runs OCR only after approval when native text is insufficient.

## Non-negotiable constraints
- No product-specific hacks.
- Preserve Web/HTML, Multimedia, Price Intelligence, OCR.space, Mistral, updater, social video downloader, and current automatic PDF mode.
- Strong identity conflicts remain hard rejects.
- Review score never overrides hard identity gates.
- In reviewed mode, only user-approved PDFs may feed evidence; an explicitly confirmed empty set means no PDF for that product.
- OCR never decides product identity by itself and never bypasses the identity gate.
- Mistral remains downstream of validated evidence.

## Current physical owners
- `src/product_intelligence/document_discovery.py`: document query generation, candidate filtering, landing inspection, PDF-link resolution, dedupe, early stop.
- `src/product_intelligence/pdf_review.py`: review candidate model, inspection, identity state, preview rendering, review score.
- `src/product_intelligence/pdf_review_shell.py`: review workspace UI, candidate list, inspection workflow, user selection.
- `src/product_intelligence/pdf_review_batch.py`: enforcement of approved PDFs during batch execution.
- Existing PDF evidence/OCR modules remain authoritative for extraction and post-OCR identity validation.

## Architecture

### 1. Product-first search ladder
Search in tiers rather than a broad 9–12-query burst. Strong identifiers (MPN/GTIN/EAN/UPC) lead. Exact brand+model comes next. Manufacturer/PDP/support pivot comes before distributors and broad fallback. Discovery stops early once an exact PDP or enough high-confidence document candidates exist.

### 2. Pre-fetch identity filter
Before deep landing inspection or PDF download, score the candidate using URL, title, snippet, domain, anchor text, and landing metadata. Reject sibling models, other strong identifiers, generic category pages, and brand-only matches before download.

### 3. Dedupe and search budget
Canonicalize URLs and track seen search results, landing pages, PDF URLs, and document hashes. Repeated results from different queries are inspected once. Use bounded query/landing budgets with quality-based early stop.

### 4. Exact PDP pivot
When an exact manufacturer or otherwise strongly validated PDP is found, inspect its support/download/manual/spec relationships immediately before continuing generic search.

### 5. Provenance binding
Every PDF discovered from a validated landing carries `DocumentProvenance`: parent URL, parent identity state/confidence, parent authority, anchor text, and discovery method. A PDF missing the MPN internally may be `IDENTITY_BOUND_BY_PROVENANCE` when it is directly linked by an exact validated parent and the PDF contains no conflicting identity. Any strong conflict still rejects.

### 6. Reviewed vs automatic PDF mode
Keep both modes. Reviewed mode is explicit and preferred in the review workspace: search → filter/rank → show candidates → stop. No extraction occurs until the user confirms selection. Automatic mode retains legacy behavior.

### 7. Multi-page PDF reader
The review preview becomes an actual reader: current page, first/previous/next/last navigation, `Page X / N`, vertical/horizontal scroll, zoom 50–200%, fit-width and fit-page, wheel scroll, Ctrl+wheel zoom. Render pages on demand and cache only rendered pages. Preview download is temporary and never evidence by itself.

### 8. OCR after approval
Inspection uses native text only. After approval and during execution, assess text quality per page and select only low-quality/spec-relevant pages for OCR. Re-run identity validation after OCR. `PENDING_OCR` is never evidence.

### 9. Page-level evidence trace
Each accepted field retains document URL, parent landing, page number, extraction method, raw snippet, canonical field, normalized value, and confidence.

## UX contract
Candidate list columns: Use, Score, Document, Type, Identity, Authority, Pages, Text, OCR, Source. States: ACCEPTED, PENDING_OCR, REJECTED, PROVENANCE_BOUND, CONFLICT. Rejected/conflict rows are not selectable. Candidates are sorted descending by review score after hard filtering.

## Success gates
- Wrong sibling-model candidates shown to the user: ideally 0.
- Wrong-model PDFs downloaded: 0.
- Cross-product contamination: 0.
- Invented specifications: 0.
- User can navigate every page and zoom/scroll without changing evidence state.
- Only approved PDFs feed reviewed-mode evidence.
- OCR happens only after approval.
- Existing Web, Multimedia, Price Intelligence, updater, social video downloader, and automatic PDF behavior remain regression-green.

## Benchmark
Use, without hardcoding production behavior, the existing QA identities:
- JBLQ350WLBLKAM
- JBLENDURRUN3BTBAM
- JBLT530CBLKAM

Measure before/after: queries, raw results, deduped candidates, wrong-model rejects, generic-page rejects, landings inspected, PDFs downloaded before review, relevant PDFs surfaced, exact PDPs, validated PDFs, and elapsed time.