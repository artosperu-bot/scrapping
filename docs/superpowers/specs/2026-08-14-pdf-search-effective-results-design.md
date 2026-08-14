# Effective PDF Search Design

## Goal

Make `Solo PDF` produce real, observable document discovery results from strong product identity, especially Part Number/MPN, before OCR.space or Mistral are involved.

## User-visible contract

When `WEB=OFF | PDF=ON`, the application must search specifically for PDFs using the strongest available identity. HTML pages may be opened only as technical bridges to discover concrete PDF links. HTML must never be accepted as final evidence in Solo PDF mode.

For each product the UI/log must expose the real stages: query issued, search method used, candidate count, landing pages inspected, PDFs discovered, download attempts, HTTP/content-type validation, identity acceptance/rejection, and final PDF count. A generic `no hubo candidatos` is insufficient by itself.

## Search architecture

1. Build Part Number-first PDF queries, starting with the human-verifiable query `<PARTNUMBER> pdf`, then quoted and document-specific variants.
2. Run the existing lightweight HTTP search first for speed.
3. If HTTP search returns no useful candidates, invoke a Playwright/Chromium browser fallback using the Chromium already bundled with the Windows app.
4. Parse actual search result links from the browser session.
5. Strong-identity-filter candidate result pages before opening them.
6. Accept direct `.pdf` results immediately as document candidates.
7. For matching product/support/download pages, open the page only to discover direct PDF links.
8. Download candidate PDFs and verify HTTP success, PDF content type or `%PDF-` signature, and product identity before evidence ingestion.
9. Only then pass accepted PDFs to native text extraction, OCR.space if required, and Mistral if enabled.

## Search strategy

Priority order:

1. MPN / Part Number
2. GTIN / EAN / UPC
3. Brand + descriptive model/name only as fallback/corroboration

Initial query set for a strong identifier `ID`:

- `ID pdf`
- `"ID" pdf`
- `"ID" filetype:pdf`
- `"ID" manual pdf`
- `"ID" datasheet pdf`
- `"ID" spec sheet pdf`
- `"ID" support downloads`

The system must not depend on Serper or another paid SERP API.

## Browser fallback

The browser fallback is a search transport, not a source of evidence. It must be encapsulated in a dedicated module so document discovery does not depend directly on Tkinter or Playwright internals.

It should use existing bundled Chromium when packaged. Browser failures must be reported distinctly from zero search results.

## PDF validation

A downloaded candidate is accepted only when:

- the download succeeds;
- the response is plausibly a PDF (`application/pdf`, `.pdf` final URL, or `%PDF-` signature);
- the candidate/document can be associated with the target product using strong identifier evidence or validated official/model evidence;
- the PDF is not obviously a generic warranty/compliance document unrelated to the requested product unless that document contains matching product identity.

## Observability

Per product, emit structured events for:

- `PDF_SEARCH_QUERY`
- `PDF_SEARCH_HTTP_RESULT`
- `PDF_SEARCH_BROWSER_FALLBACK`
- `PDF_SEARCH_BROWSER_RESULT`
- `PDF_LANDING_INSPECTED`
- `PDF_LINK_DISCOVERED`
- `PDF_DOWNLOAD_ATTEMPT`
- `PDF_DOWNLOAD_OK`
- `PDF_DOWNLOAD_REJECTED`
- `PDF_IDENTITY_ACCEPTED`
- `PDF_IDENTITY_REJECTED`

The terminal summary must include counts for queries, search results, landing pages, discovered PDFs, downloaded PDFs, accepted PDFs, rejected PDFs, and errors.

## Credential persistence

OCR.space and Mistral credentials remain stored through the existing OS keyring service `ProductIntelligence`; updates must not overwrite or clear them. Non-secret provider settings remain in `%LOCALAPPDATA%\\ProductIntelligence\\settings.json`.

A regression test must prove that updater/install-path replacement logic does not target either the keyring or the `%LOCALAPPDATA%` settings path.

## Acceptance criteria

For the regression identities `JBLQ350WLBLKAM`, `JBLENDURRUN3BTBAM`, and `JBLT530CBLKAM`:

- Solo PDF must issue visible Part Number-first PDF queries.
- When HTTP search yields zero, browser fallback must execute instead of returning immediately.
- Any discovered landing page must only act as a bridge to concrete PDF links.
- The pipeline must expose whether a PDF URL was found and whether a PDF was downloaded.
- OCR/Mistral must not be blamed or invoked before an accepted PDF exists.
- Credentials/settings must survive normal application upgrades.

No unrelated changes to Multimedia, Price Intelligence, updater behavior, or general Web/HTML evidence are in scope.