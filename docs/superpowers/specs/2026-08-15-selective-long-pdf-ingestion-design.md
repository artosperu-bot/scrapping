# Selective Long-PDF Ingestion Design

## Goal
Reduce PDF-processing latency without losing useful product specifications.

## Approved behavior
- PDFs with 10 pages or fewer are processed completely.
- PDFs with more than 10 pages are not rejected only for being long.
- Long PDFs use a cheap native-text scan across pages, then fully process at most 15 pages.
- Priority order: first 8 pages, pages containing the exact model/MPN/strong identifiers, then pages with technical-specification terms.
- OCR is attempted only on selected pages, never indiscriminately across the whole long document.
- The objective is useful commercial/technical specifications, not exhaustive service-manual detail.
- If selected pages do not provide sufficient material evidence, the existing fail-closed behavior remains.
- No product- or brand-specific exceptions.

## Scope
Modify PDF extraction and pass identity/target terms from document ingestion. Add focused regression tests. Do not change automatic brand/model discovery or evidence-authority policy.
