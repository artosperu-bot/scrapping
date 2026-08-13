# PDF Evidence and Attribute Alignment Implementation Plan

Goal: add generic PDF evidence to Scraping Excel without changing the existing HTML-first contract.

Architecture: detect and validate product PDFs, extract text with PyMuPDF, use OCR only when text is insufficient, convert accepted facts into existing Evidence objects, and let current attribute/value gates decide what reaches Excel.

Tasks:
1. Add `pdf_evidence.py` for PDF discovery, download validation, and product-identity checks.
2. Add `pdf_extract.py` for page-level PyMuPDF extraction with optional OCR/Documents fallback.
3. Add `pdf_attribute_alignment.py` to turn document labels/values into generic Evidence with provenance.
4. Integrate PDF enrichment in `batch.py` after normal web extraction and before Excel mapping; `use_pdf_evidence` defaults True.
5. Add `Usar PDFs como evidencia` in Scraping Excel and freeze it in the execution snapshot.
6. Emit PDF lifecycle events through the existing audit system.
7. Run generic MPN, GTIN/EAN and model/name fallback tests plus full regression.
8. Open PR, require CI PASS, merge, then require Windows Build EXE PASS.

Constraints: no product-specific runtime rules; wrong PDFs never fill attributes; PDF/OCR failures are non-fatal; preserve identity, exact-product, outputs, Multimedia and Price contracts.
