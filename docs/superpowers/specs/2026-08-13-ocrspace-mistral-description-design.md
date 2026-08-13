# Product Intelligence — OCR.space + Mistral Description Design

Date: 2026-08-13
Baseline main: `82b6aac1525108491f97ddaccca71ab1d85d9725`

## Goal
Integrate OCR.space as the remote OCR fallback for scanned PDF/image evidence and Mistral `mistral-small-latest` only as an optional commercial-description narrator, without duplicating the current PDF, OCR, description, Excel, audit, or desktop architecture.

## Non-goals
- Do not replace PyMuPDF-first PDF extraction.
- Do not replace deterministic attribute resolution.
- Do not let Mistral perform OCR or invent product facts.
- Do not touch Multimedia or Price Intelligence behavior.
- Do not make either provider mandatory for normal scraping.

## Existing seams to preserve
- `pdf_evidence.py`: discovery/download/context/events.
- `pdf_extract.py`: PyMuPDF-first page extraction with OCR fallback seam.
- `ocr_adapter.py`: OCR boundary.
- `ProductIdentity`, `Evidence`, `ProductRecord`: canonical domain models.
- `derive_description()` + `marketplace_resolution.py`: existing description-resolution path.
- `excel_mapper_v8.py`: final deterministic Excel writer.
- `ExecutionSnapshot` + structured audit: run isolation and observability.

## Target flow
`Validated source -> PDF/image document -> PyMuPDF when possible -> OCR.space only when text is insufficient -> existing identity/evidence validation -> ProductRecord -> description requested by Excel -> validated facts -> mistral-small-latest -> anti-invention guard -> existing marketplace resolution -> Excel`

OCR output never goes directly from raw OCR to Mistral. It must first pass the current product identity/evidence pipeline.

## OCR.space integration
Add an OCR provider implementation behind the existing OCR adapter. Provider selection is configuration-driven.

Priority for a PDF page:
1. native PDF text via PyMuPDF;
2. OCR.space when native text is insufficient and a valid OCR.space credential is configured;
3. existing local PaddleOCR only when installed/configured as fallback;
4. fail closed with empty OCR result, while the rest of the product run continues.

OCR.space calls run in worker threads, never the Tkinter UI thread. Timeouts/network/quota/provider errors are classified and audited without exposing secrets.

## Mistral integration
Mistral is used only for narration of a product description. It receives:
- validated brand/model/MPN identity;
- a bounded list of already accepted product facts;
- no price, stock, seller data, rejected evidence, unresolved conflicts, or unvalidated raw OCR text.

Model: `mistral-small-latest`.

Required prompt constraints:
- use only supplied information;
- do not invent specifications, compatibility, materials, certifications, or benefits not derivable from supplied facts;
- do not introduce price or stock;
- preserve exact brand/model;
- natural Spanish;
- coherent commercial prose instead of a copied technical list;
- avoid redundant repetition.

The existing deterministic `derive_description()` remains the permanent fallback when Mistral is disabled, unavailable, rejected, times out, or fails validation.

## Anti-invention guard
Before accepting a Mistral description:
- reject altered brand/model/MPN;
- reject new numeric values/units absent from allowed facts;
- reject price/stock/seller claims;
- reject unsupported compatibility/material/certification claims when they introduce facts not represented in the allowed fact set.

On rejection, use the existing deterministic description and emit an audit event.

## Configuration UI
Add one global `Configuración` workspace to the existing modern desktop shell; do not create separate OCR and Mistral screens.

Sections:

### OCR.space
- masked API key field;
- status: `CONECTADO`, `RECHAZADO`, `SIN CONFIGURAR`, or classified error;
- `Probar conexión` button.

### Mistral
- masked API key field;
- model display/default: `mistral-small-latest`;
- status;
- `Probar conexión` button.

Connection tests are real provider calls executed off the UI thread. A non-empty key is never sufficient to report `CONECTADO`.

## Credential persistence
Create one generic credential-store abstraction. Secrets must not be stored in repository files, output folders, audit logs, or plain-text settings JSON.

Preferred backend on Windows: Windows Credential Manager through a small credential-store abstraction. If packaging validation proves that backend unsuitable, use Windows DPAPI behind the same interface.

Non-secret settings (provider enablement, model, timeout values) may be persisted under the per-user Product Intelligence application-data directory.

At restart:
- credentials remain registered;
- fields display masked placeholders/state, not plaintext keys;
- user can replace/delete credentials;
- no re-entry is required every launch.

## Provider error taxonomy
Shared statuses:
- `EMPTY_KEY`
- `AUTH_REJECTED`
- `TIMEOUT`
- `NETWORK_ERROR`
- `QUOTA_OR_RATE_LIMIT`
- `PROVIDER_ERROR`
- `INVALID_RESPONSE`
- `CONNECTED`

The UI converts these to Spanish messages. Audit stores provider/status/duration only, never authorization headers or secrets.

## Files expected to change
- `src/product_intelligence/ocr_adapter.py`
- `src/product_intelligence/pdf_extract.py`
- `src/product_intelligence/field_derivations.py` or its description call seam
- `src/product_intelligence/marketplace_resolution.py` only if a clean narrator injection point is required
- `src/product_intelligence/pdf_desktop.py` / final desktop shell for run settings
- `src/product_intelligence/modern_desktop.py` or the final inherited shell for Configuración navigation
- `ProductIntelligence.spec` only as needed for packaging the credential backend/new modules
- tests and release gates

## New focused modules
Only where no equivalent exists:
- `credential_store.py`
- `provider_settings.py`
- `provider_status.py` or equivalent shared error classification
- `ocr_space_client.py`
- `mistral_client.py`
- `description_narrator.py`

No second PDF pipeline, second Excel writer, second audit system, or second product model.

## Testing gates
1. existing full regression remains green;
2. PDF with usable native text never calls OCR.space;
3. scanned/empty-text PDF invokes OCR.space when enabled;
4. OCR.space invalid key/timeout/quota/network errors fail non-fatally;
5. OCR result still passes current identity/evidence protections;
6. credentials persist across simulated restart and are never returned/logged in plaintext;
7. connection status requires a real provider response;
8. Mistral receives only validated identity/facts;
9. grounded Mistral description is accepted;
10. invented number/spec/price/stock/identity change is rejected;
11. deterministic description fallback works when Mistral is disabled/down;
12. Excel/Multimedia/Price isolation remains intact;
13. Windows CI, desktop smoke, PyInstaller, executable verification and artifact upload pass before release.

## Success criteria
The user configures OCR.space and Mistral once, verifies each credential with a real connection test, restarts the EXE without re-entering keys, obtains OCR fallback only when needed, and gets Mistral-authored commercial descriptions only from validated product facts. Existing scraping, PDF text extraction, media, prices, identity guards, audit, and Excel behavior continue to work when either provider is unavailable.
