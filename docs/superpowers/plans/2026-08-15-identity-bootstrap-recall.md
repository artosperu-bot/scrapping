# Identity + PDF Discovery Architecture — v0.10.19

> **Release target:** `release/windows`. `main` remains untouched.

## Goal

Resolve product identity from unknown input before deep document extraction, then use all available strong identifiers to discover the correct technical PDFs without weakening fail-closed validation.

The production system must work when the input provides any useful combination of:

- MPN / Part Number
- EAN
- UPC
- GTIN
- SKU
- model
- product name
- manual source URL

No product→brand or product→domain hardcodes are allowed.

## Canonical flow

```text
RAW INPUT
→ GENERIC WEB IDENTITY DISCOVERY
→ CANDIDATE URLS
→ SOURCE ROLE / PAGE TYPE
→ IDENTITY EVIDENCE
→ CROSS-SOURCE IDENTITY RESOLUTION
→ OFFICIAL AUTHORITY DISCOVERY
→ DEEP WEB SEARCH
→ PDF SEARCH MATRIX
→ HTML TECHNICAL PAGE AS OPTIONAL BRIDGE
→ REAL PDF URL
→ PDF CONTENT IDENTITY VALIDATION
→ EXTRACTION
→ EVIDENCE POLICY / CONSENSUS
→ PRODUCT RECORD OR FAIL_CLOSED
```

Discovery is permissive. Validation is strict.

## WEB behavior

The normal WEB path remains separate from the PDF query matrix.

- Generic web search continues to discover product pages and technical/support pages.
- A manually supplied URL can be tried directly.
- Manual URLs are not trusted automatically; they pass the same page-type, identity and authority gates.
- Sellers, marketplaces, publishers, social pages and support databases may contribute discovery evidence, but their site names do not automatically become the product brand.
- A hostname containing the brand token is not proof of manufacturer authority.

## Identity resolution

Identity is resolved before it is used to narrow document search.

Higher-value evidence includes:

1. structured `brand`, `manufacturer`, `model`, `mpn`, `gtin`, `ean`, `upc`;
2. exact strong-identifier binding on a material product page;
3. evidence-backed manufacturer/support authority;
4. independent-domain corroboration;
5. title/snippet evidence only as weaker discovery evidence.

### False-brand guards

The resolver must reject generic candidates such as:

- seller / marketplace names when they are merely the source;
- UI boilerplate;
- commerce condition words such as `used`, `refurbished`, `renewed`, `open-box`;
- product-format/type descriptors such as `multi-function`, `all-in-one`, `A4`;
- sibling or near-identical alphanumeric model/MPN codes being mistaken for brands.

One domain cannot inflate confidence by repeating the same evidence across many URLs.

## PDF search matrix

PDF discovery is identifier-first. It does not rely only on a product name and it does not stop at the first available identifier.

For identity values such as:

```text
brand = ExampleTech
model = Rugged 77
mpn = ZX-4109
ean = 1234567890123
upc = 012345678905
gtin = 01234567890128
```

the query builder can generate a bounded, deduplicated sequence including:

```text
ZX-4109 pdf
"ZX-4109" filetype:pdf
"1234567890123" filetype:pdf
"012345678905" filetype:pdf
"01234567890128" filetype:pdf

"ZX-4109" "Rugged 77" filetype:pdf
"1234567890123" "Rugged 77" filetype:pdf

"ExampleTech" "ZX-4109" filetype:pdf

"ZX-4109" datasheet pdf
"ZX-4109" manual pdf
"ZX-4109" specifications pdf
```

The first plain `<primary identifier> pdf` query is preserved because it is human-verifiable and some search transports return useful results even when advanced operators are ignored.

All available MPN/EAN/UPC/GTIN values participate; the PDF path must not silently discard EAN/UPC/GTIN because an MPN also exists.

## Official-domain acceleration

`site:` queries are allowed only after a domain has evidence-backed authority.

Examples:

```text
site:exampletech.com "ZX-4109"
site:exampletech.com "ZX-4109" filetype:pdf
site:exampletech.com "Rugged 77" datasheet
site:exampletech.com "Rugged 77" manual
```

`site:` narrows discovery. It never makes a source official by itself.

## HTML → PDF bridge

An HTML technical/support page may be used as a bridge:

```text
validated technical/support HTML
→ inspect direct document links
→ rendered/browser fallback if needed
→ real .pdf URL
```

The HTML page itself is never recorded as a PDF.

## PDF validation

A `.pdf` URL or a search-result match is not sufficient evidence.

The downloaded PDF must bind to the resolved product through sufficient content evidence, using combinations of:

- MPN / Part Number
- EAN / UPC / GTIN
- model
- brand/manufacturer
- product name/context

An incidental numeric collision is rejected. For example, an unrelated legal document containing a number similar to a product code cannot become product evidence merely because the string appears in the PDF.

## Source options

WEB, PDF, OCR and Mistral remain independent execution controls.

For identity/search QA:

```text
WEB = ON
PDF = ON when testing document discovery
OCR = OFF
MISTRAL = OFF
```

OCR/Mistral are downstream helpers and must not rescue an incorrect product identity.

## Manual URLs

Manual source URLs remain supported.

- WEB URL + WEB enabled → normal page validation pipeline.
- Direct PDF URL + PDF enabled → PDF identity/content validation pipeline.
- Supplying a URL never bypasses fail-closed gates.

## Performance rules

Apply bounded work and reuse:

- query dedupe;
- canonical URL dedupe;
- registrable-domain dedupe for identity voting;
- candidate reuse;
- bounded page probes;
- bounded PDF query prefix;
- early success after strong evidence;
- no aggressive early fail when useful discovery paths remain.

## QA gates before v0.10.19 source-validation integration

The source-validation/identity PR is not releasable until fresh CI proves:

```text
unit/full CI = PASS
PDF Search Integration Smoke = PASS
6-case identity benchmark = PASS target 6/6
20-brand identity benchmark = PASS target 20/20
false brand = 0
false manufacturer = 0
cross-product contamination = 0
non-material evidence = 0
hardcoded product exceptions = 0
OCR calls during identity benchmark = 0
Mistral calls during identity benchmark = 0
Source Validation benchmark = PASS
```

If a live case fails, fix the general failure class and rerun. Do not change the QA oracle to hide a production error.

## Integration / release

The already validated workspace/UI organization is integrated independently into `release/windows`.

The identity/source-validation/PDF work remains isolated until its gates pass. When they pass:

1. rebase/merge against current `release/windows`;
2. run full CI and live smoke/benchmark gates on the integrated commit;
3. bump application version to `0.10.19` using the repository's existing release mechanism;
4. build Windows artifacts;
5. verify updater/release metadata and public asset;
6. only then tell users that v0.10.19 is ready to update.
