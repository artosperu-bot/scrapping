# Generic Excel Intake & Observability Design

## Goal
Make ProductIntelligence accept product rows from heterogeneous Excel templates without depending on fixed sheet names, fixed header rows, fixed column indexes, categories or marketplaces, while keeping SEARCH/scraping unchanged.

## Confirmed current failures
- `batch.detect_items()` discards a sheet before reading product rows when fewer than 3 header fields are present.
- Header recognition is exact-canonical enough that aliases such as `EAN/UPC`, `Model No`, `manufacturer partnumber`, `sku_seller` can be missed.
- Product-table detection and template-contract execution-sheet detection use different rules.
- Pre-SEARCH rejected rows have no explicit reason, so `not searched` and `searched with no candidates` are indistinguishable.
- Excel analysis runs synchronously from the Tkinter event handler and can make the executable appear frozen on large/complex workbooks.

## Architecture
Use one read-only intake pipeline before SEARCH:

`WorkbookAnalyzer -> SheetClassifier -> HeaderResolver -> RowIdentityResolver -> RowDecision -> ProductIdentity -> SEARCH`

SEARCH receives only `ProductIdentity`; it never receives marketplace, sheet or column-specific concepts.

## Sheet classification
Every worksheet is inspected. A sheet is scored using signals rather than its title:
- header semantic score;
- number of candidate identity columns;
- repeated non-empty rows below the header;
- identity-looking values below candidate columns;
- data density.

Auxiliary/help/list sheets are rejected by evidence (no repeated product identities / low table score), never by name.

A one-column sheet may be a valid product sheet when the header maps to identity and product-like values repeat below it. There is no minimum-three-columns gate.

## Header resolution
Header-row selection scores both header semantics and downstream row evidence. It scans the first 30 rows and may use nearby upper rows as context/description.

Header normalization is separator/accent/case-insensitive and strips marketplace numeric suffixes. Identity aliases are grouped into canonical concepts:
- `part_number`: MPN, part number, partnumber, manufacturer part number/partnumber, PN, model/model number/model no/modelo when used as the strongest manufacturer identifier;
- `gtin`: EAN, UPC, EAN/UPC, GTIN, barcode, codigo/código de barras;
- `sku`: SKU, seller SKU, sku_seller, merchant SKU.

The external header is preserved in audit output; normalization never rewrites the source workbook.

## Identity resolution
Priority for initial research:
1. explicit manufacturer part number / MPN;
2. EAN / UPC / GTIN;
3. model-like manufacturer identifier;
4. seller SKU as last-resort fallback;
5. product name only for backward compatibility when no stronger identity exists.

Brand, name, description, category, images and marketplace attributes are optional. One usable identity value is enough to create a product.

Values such as `TE-2128S`, `IPC-S042`, and `JBLQ350WLBLKAM` are valid by themselves.

## Observability
The intake analyzer returns per-sheet and per-row diagnostics without changing SEARCH behavior:
- `sheet_detected`, `sheet_score`, `sheet_accepted`, `sheet_rejection_reason`;
- `header_row_detected`, `raw_headers`, `normalized_headers`;
- detected `part_number_column`, `gtin_column`, `sku_column`;
- `product_row`;
- raw/normalized identity values;
- `identity_type`, `identity_value`;
- `row_accepted`, `rejection_reason`;
- `search_requested`, `search_query`.

Stable rejection codes include `NO_HEADER`, `NO_PRODUCT_ROWS`, `NO_IDENTITY_COLUMN`, `NO_IDENTITY_VALUE`, `IDENTITY_PLACEHOLDER`, and `ROW_REJECTED_BEFORE_SEARCH`.

## SEARCH boundary
`batch.scrape_item()` and `discovery.search_web()` remain unchanged unless a test proves a regression. Intake creates `BatchItem` objects containing normalized `ProductIdentity`; existing SEARCH consumes them as before.

## UI responsiveness
Workbook analysis must not execute on Tkinter's UI thread. `ANALIZAR EXCEL` starts a daemon worker, updates the UI only through `after(...)`, disables duplicate analysis while running, and always reaches a terminal UI state (success or error).

No background worker survives application shutdown; this is UI responsiveness, not daemonized job execution.

## Compatibility
- Base: current `release/windows` after PR #31.
- `main` remains untouched.
- Existing v0.10.4+ scraping, canonical/evidence, PDF, Multimedia, Price Intelligence, OCR.space, Mistral and updater behavior is preserved.
- Existing large marketplace templates remain supported.
- Manual product identity mode remains supported.

## Tests
Add regression fixtures generated in tests for:
- one-column `Part Number` workbook;
- aliases with case/accents/separators/numeric marketplace suffixes;
- `EAN/UPC` only;
- model-only identifiers;
- SKU-only fallback;
- auxiliary sheet plus real product sheet;
- misleading header row above the real table;
- rejected row with explicit reason;
- SEARCH query audit from accepted identity;
- desktop analysis dispatch outside the UI thread;
- full existing suite.
