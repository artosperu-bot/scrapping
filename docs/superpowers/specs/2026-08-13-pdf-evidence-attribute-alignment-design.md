# Product Intelligence — PDF Evidence and Attribute Alignment Design

Date: 2026-08-13

## Goal
Add a generic PDF evidence fallback to Scraping Excel so the system can detect, validate, download, extract and use product PDFs to improve attribute completion without coupling behavior to any brand, model or category.

## User option
Scraping Excel exposes a checkbox **Usar PDFs como evidencia**, enabled by default. Disabling it preserves the current non-PDF flow.

## Processing order
1. Existing HTML/web extraction remains first.
2. Discover candidate PDF links from validated product sources and dynamic pages.
3. Validate each PDF against the canonical product identity before using it.
4. Download accepted PDFs to the product evidence area.
5. Extract text with PyMuPDF first.
6. If a page has no useful text, use OCR only for that page when the OCR capability is available.
7. If document/table parsing is difficult and the optional documents capability is available, it may be used as an additional fallback.
8. Align extracted labels/values to the attributes requested by the Excel template.
9. Accept a value only when product identity, attribute meaning, value and unit are compatible.
10. Store source URL, local PDF, page, original label, extraction method and confidence as evidence.

## General-product requirement
No runtime rule may depend on JBL, HyperX, Ulefone or any fixture product. Matching must work from generic identity fields such as MPN/Part Number, GTIN/EAN/UPC, brand, model and normalized product name.

## PDF discovery
Candidate PDFs may come from direct `.pdf` links, anchors whose text suggests manuals/spec sheets/datasheets/technical sheets, redirects to PDF content, or links discovered after browser rendering. HTTP/HTML discovery is preferred; Playwright remains fallback for dynamic pages.

## PDF identity validation
A PDF is accepted only when document evidence is compatible with the active product identity. Strong signals include exact MPN/Part Number, GTIN/EAN/UPC, exact model plus brand, or a sufficiently specific normalized product title. Family/generation conflicts reject the document. A PDF that cannot be tied confidently to the active product may be downloaded only if needed for diagnostics, but it must not populate attributes.

## Text extraction and OCR fallback
PyMuPDF is the default extractor because it is already a core dependency. OCR is not used when a usable text layer exists. OCR is page-scoped and invoked only when text is empty or clearly insufficient. Failure or absence of OCR must not fail the Scraping Excel job.

## Attribute alignment
Introduce a generic alignment layer that maps requested Excel attributes to semantically equivalent document labels. Examples are illustrative only:
- Autonomía ↔ Battery life ↔ Playback time
- Peso del producto ↔ Net weight ↔ Weight
- Capacidad de batería ↔ Battery capacity
- Tamaño del driver ↔ Driver size ↔ Speaker driver
- Dimensiones ↔ Product dimensions ↔ Size

Alignment must not rely only on fuzzy label similarity. It also validates value shape, unit family, local context and product identity. Ambiguous mappings remain unresolved instead of being guessed.

## Evidence model
For every accepted PDF-derived fact retain at least:
- product canonical identifier
- requested attribute
- normalized value
- normalized unit when applicable
- original document label/text
- source URL
- local PDF path
- page number
- extraction method: TEXT, OCR or DOCUMENTS
- confidence / validation result

The existing evidence/audit architecture remains the source of truth; PDF facts become another evidence source rather than a parallel datastore.

## Error handling
PDF discovery, download, parsing, OCR and alignment errors are non-fatal fallbacks. They are logged in Auditoría with the relevant run ID, product and stage. One broken PDF must not block other sources or products.

## UI behavior
The option lives inside Scraping Excel, not as a separate top-level process. The user can see PDF-related events in Auditoría, including PDF_FOUND, PDF_ACCEPTED, PDF_REJECTED, PDF_DOWNLOADED, PDF_TEXT, PDF_OCR, ATTRIBUTE_ALIGNED and PDF_ERROR (exact internal event names may follow existing audit conventions).

## Preservation
Do not rewrite the existing extraction, identity, media or price engines. Preserve Excel-first behavior, canonical identity protections, source priority, current output contracts and the independent Multimedia/Precios workflows.

## Testing
Tests must cover:
1. direct PDF discovery;
2. non-`.pdf` URL returning PDF content;
3. exact-product acceptance;
4. wrong-model/family rejection;
5. PyMuPDF extraction path;
6. OCR invoked only when text is insufficient;
7. OCR unavailable without failing the job;
8. attribute alias alignment with compatible units;
9. ambiguous attribute rejection;
10. provenance includes URL/page/method;
11. option enabled by default and disabled path preserves old behavior;
12. generic products using MPN, GTIN and model/name fallback;
13. full regression and Windows build gates.

## Release gate
No release is closed until full CI regression and Build Windows EXE both pass on the exact implementation SHA, including modern desktop smoke, bundled Chromium, PyInstaller, executable verification and artifact upload.

## Success criteria
When a valid product PDF exists, Scraping Excel can use it as additional evidence to fill requested attributes more reliably. When there is no PDF, a wrong PDF, an unreadable PDF, or OCR is unavailable, the existing scraping flow continues safely without invented values or cross-product contamination.
