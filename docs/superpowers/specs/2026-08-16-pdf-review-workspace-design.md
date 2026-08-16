# PDF Review Workspace Design

## Goal
Add a transparent PDF review step to ProductIntelligence so the user can see which technical documents were discovered, preview them, decide which ones may be used, and only then allow selected PDFs to feed the existing evidence pipeline. OCR remains a fallback for insufficient native PDF text; Mistral remains downstream of validated facts.

## User workflow
1. Open **Revisión PDF**.
2. Select a product already detected in the Excel workflow.
3. Click **Buscar PDFs**.
4. ProductIntelligence discovers candidate technical PDFs using the existing document discovery stack.
5. Candidates appear in a table with document type, preliminary score, source/host and review state.
6. Selecting a row downloads that PDF to the output review cache, validates identity, measures native-text coverage and renders a first-page preview.
7. The detail panel shows identity result, page count, native-text size and whether OCR is recommended.
8. The user toggles which documents should be used and clicks **Confirmar selección**.
9. During Scraping Excel, confirmed products use only the approved PDF URLs. Automatic HTML/Web acquisition remains unchanged. Automatic PDF following/discovery is disabled only for that confirmed product.
10. OCR runs only through the existing PDF extraction path when native text is insufficient and OCR is enabled. Mistral continues to consume validated facts only.

## Architecture
### `pdf_review.py`
Tk-independent service responsible for:
- discovering candidate PDFs via `discover_product_documents`;
- classifying document type;
- computing a transparent preliminary score from discovery hints;
- downloading one candidate for inspection;
- validating PDF/product identity with `validate_pdf_identity`;
- extracting native text with PyMuPDF for review metrics;
- deciding whether OCR is recommended without invoking OCR;
- rendering a preview PNG for the first page.

The review score is informational only. Identity gates remain authoritative. A high score never bypasses a failed identity result.

### `pdf_desktop.py`
Adds a dedicated `Revisión PDF` workspace with:
- product selector;
- **Buscar PDFs** action;
- candidate Treeview;
- **Usar / quitar** action;
- **Confirmar selección** action;
- right-side PDF preview;
- metadata/status panel.

All network/PDF work runs off the Tk thread. UI updates return through `after()`.

### Batch selection enforcement
`BatchItem` gains reviewed PDF URLs plus an enforcement flag. When enforcement is enabled for a product:
- selected PDFs are inserted as explicit PDF candidates;
- HTML/Web sources continue normally;
- `ProductPipeline.process_url(... include_pdfs=False)` prevents automatic PDFs from HTML pages;
- automatic direct PDF discovery is skipped;
- PDF gap-filling discovery is skipped;
- only the user-approved PDFs can contribute PDF evidence.

When review is not confirmed for a product, current automatic PDF behavior is preserved.

## OCR and Mistral
- Review inspection never spends OCR API quota.
- `ocr_recommended=True` is derived from low/empty native text density.
- During the actual run, selected PDFs pass through the existing PDF extraction logic. If OCR is enabled and native text is insufficient, the existing OCR fallback may run.
- Mistral remains downstream and can only operate on already validated canonical facts. No new technical extraction role is added.

## Error handling
- Discovery failure: show explicit status, keep existing data untouched.
- Download/HTTP failure: mark candidate as inspection error; it cannot silently become approved evidence.
- Identity rejection: display `REJECTED` and prevent accidental acceptance.
- Preview render failure: metadata can still be shown, but no evidence is accepted merely because preview failed.
- Zero approved PDFs with confirmed review means no PDF evidence for that product; Web/HTML can still resolve the product.

## Testing
1. Service unit tests for document-type score, identity inspection, OCR recommendation and PNG preview output using an in-memory/generated PDF.
2. Batch contract tests proving reviewed selection disables unapproved automatic PDF discovery while Web remains available.
3. Desktop contract tests proving the new workspace, candidate table, preview, selection and confirmation controls exist and that reviewed selections are forwarded to `run_batch`.
4. Full regression suite before merge.

## Non-goals
- No OCR during preview.
- No Mistral extraction from raw PDF text.
- No weakening identity/evidence gates.
- No changes to Price Intelligence, Multimedia or social video downloader.
- No mandatory review: products without a confirmed selection retain automatic PDF behavior.
