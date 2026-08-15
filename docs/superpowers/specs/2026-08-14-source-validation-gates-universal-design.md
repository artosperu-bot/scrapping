# Universal Source Validation Gates — Design Spec

Date: 2026-08-14
Base branch: `release/windows`
Scope: scraping/evidence acceptance only. OCR.space and Mistral remain disabled for the benchmark and are not used to rescue bad sources.

## 1. Goal

Make ProductIntelligence conservative, general, and trustworthy across brands/categories by separating **discovery** from **permission to contribute evidence**.

The system may discover many URLs, but a URL must pass explicit gates before it can populate product attributes. When evidence is insufficient or conflicting, the system must leave the field empty rather than infer a plausible value.

Primary rule: **precision first / fail closed**.

## 2. Problems this design must eliminate

Observed real benchmark failures:

1. A JBL category page was accepted as if it were the exact Tune 530C product page.
2. `applefixpros.com` was classified as manufacturer because the hostname contained the brand string `apple`.
3. A Samsung update/notification page was accepted as if it were a technical product page.
4. Ulefone Armor 26 Ultra evidence was accepted while the requested product was Armor 22.
5. Lenovo demonstrated the desired path: exact support/product identity + technical PDF can provide useful evidence without OCR or Mistral.
6. PDF parsing can still emit noisy fragments as attribute values, so extraction confidence must be separate from source identity confidence.

No solution may hardcode these brands or product names. These are regression examples only.

## 3. Non-goals

- Do not add brand-specific allowlists for JBL, Apple, Samsung, Lenovo, Ulefone, etc.
- Do not require Serper or another paid SERP provider.
- Do not use OCR.space or Mistral to decide whether an incorrect source should be trusted.
- Do not rewrite the complete scraper framework.
- Do not replace the current SEARCH layer unless a focused adapter is needed.
- Do not fill missing fields with guesses.

## 4. Target architecture

```text
SEARCH / DISCOVERY
        ↓
CANDIDATE URL
        ↓
PAGE TYPE GATE
        ↓
IDENTITY GATE
        ↓
AUTHORITY GATE
        ↓
EXTRACTION
        ↓
EVIDENCE QUALITY GATE
        ↓
CROSS-SOURCE CONSENSUS
        ↓
PRODUCT RECORD / EMPTY FIELD
```

Discovery answers: **Where might useful information exist?**

Validation answers: **Is this source allowed to contribute this evidence to this exact product?**

These responsibilities must not be conflated.

## 5. Gate 1 — Page Type

Introduce a normalized page/document classification:

- `PRODUCT`
- `PRODUCT_VARIANT`
- `DOCUMENT`
- `SUPPORT_PRODUCT`
- `CATEGORY`
- `SEARCH_RESULTS`
- `UPDATE`
- `LEGAL`
- `ACCOUNT`
- `GENERIC_SUPPORT`
- `UNKNOWN`

### Evidence permissions

`PRODUCT`, `PRODUCT_VARIANT`, `DOCUMENT`, and `SUPPORT_PRODUCT` may contribute material product evidence **only after identity passes**.

`CATEGORY`, `SEARCH_RESULTS`, `UPDATE`, `LEGAL`, `ACCOUNT`, `GENERIC_SUPPORT`, and `UNKNOWN` may be used for navigation/discovery/identity hints but must not directly populate technical attributes.

### Classification signals

Use multiple deterministic signals, not a single keyword:

- schema.org / JSON-LD types (`Product`, `ProductGroup`, `ItemList`, `BreadcrumbList`, `Article`, etc.)
- URL path patterns and canonical URL
- page title / H1 relationship
- number of distinct product entities on page
- repeated product-card patterns
- presence of specification sections/tables
- support/download context
- document MIME/type for PDF

A page containing the requested MPN is not automatically a product page.

## 6. Gate 2 — Exact Product Identity

Create an `IdentityAssessment` independent from extraction. It receives the requested `ProductIdentity` plus signals extracted from the candidate.

### Strong identifiers

Priority:

1. MPN / manufacturer part number
2. GTIN / EAN / UPC
3. exact model code
4. product name + brand only when no strong identifier exists

### Outcomes

- `EXACT`
- `COMPATIBLE`
- `AMBIGUOUS`
- `CONFLICT`
- `INSUFFICIENT`

### Required behavior

- Any conflicting strong identifier causes `CONFLICT` and blocks material evidence.
- If the requested model is `Armor 22` and the candidate's dominant product identity is `Armor 26 Ultra`, the source is rejected even if the brand/domain is correct.
- The input identity must never overwrite contradictory evidence from the page to create an artificial match.
- Model-family similarity is not enough when exact product codes differ.
- For products without MPN/GTIN, brand + normalized model/name can reach `COMPATIBLE`, but not `EXACT` unless corroborated by structured or repeated product-level signals.

## 7. Gate 3 — Source Authority

Replace hostname substring inference with evidence-based authority classification.

Normalized classes:

- `manufacturer`
- `manufacturer_support`
- `authorized_distributor`
- `retailer`
- `marketplace`
- `technical_database`
- `third_party`
- `unknown`

### Manufacturer requirements

A domain must not become `manufacturer` simply because its hostname contains the brand.

Manufacturer confidence should be built from a combination of:

- canonical/organization structured data identifying the brand/company
- brand-owned site navigation/footer/legal organization signals
- consistent brand domain across multiple product pages
- explicit manufacturer organization in structured metadata
- known same-origin support/product relationships discovered from the candidate itself

No single weak signal is enough.

### Authority is separate from identity

An official Samsung page for the correct model can still be `UPDATE` and therefore unable to populate technical specs.

A retailer can provide evidence if identity is exact, but its evidence receives lower authority than an exact manufacturer/product/document source.

## 8. Extraction strategy

Extraction order:

1. JSON-LD / Microdata / RDFa (`extruct` already exists in the project)
2. explicit specification tables / definition lists / product-detail blocks
3. clean main-content extraction
4. constrained DOM heuristics
5. PDF native text extraction

Recommended lightweight additions to evaluate during implementation:

- `trafilatura` for main-content isolation and boilerplate reduction
- `selectolax` for fast DOM parsing where useful

These libraries are optional implementation details; they must only be introduced if tests demonstrate measurable benefit and no regression.

### Noise rejection

Do not expose generic telemetry/configuration keys as product specs, e.g.:

- `currencyCode`
- authentication/session flags
- taxonomy/navigation state
- analytics/customer IDs
- generic page metadata

Extraction must emit evidence candidates with confidence and provenance; it must not directly guarantee acceptance.

## 9. Evidence Quality Gate

Each extracted fact must carry:

- attribute semantic
- normalized value
- source URL
- source type/page type
- source authority class
- identity assessment
- extraction method
- confidence

Material evidence is accepted only when:

1. page/document type permits material evidence;
2. identity is `EXACT` or sufficiently strong `COMPATIBLE`;
3. there is no strong identifier conflict;
4. extraction method is suitable for the semantic;
5. confidence crosses the semantic-specific threshold.

Reject malformed snippets such as sentence fragments being treated as interface/model values when the extraction structure does not support that mapping.

## 10. Cross-source consensus

Use source ranking, not winner-by-order.

### Proposed precedence

1. exact manufacturer product page / exact manufacturer technical document
2. exact manufacturer support product page
3. exact authorized distributor / high-quality technical database
4. exact retailer
5. other exact third-party sources

### Acceptance rules

- One exact high-authority source may be enough for ordinary factual fields.
- Lower-authority sources should require corroboration when the field is material or when confidence is weak.
- If two strong sources materially conflict, output remains empty for that field and the conflict is recorded.
- Do not silently choose a value merely because it appeared first or most recently.

## 11. Fail-closed behavior

If a field cannot be justified, the final output must be empty/null and its resolution audit should explain one of:

- `NO_ELIGIBLE_SOURCE`
- `IDENTITY_CONFLICT`
- `PAGE_TYPE_NOT_MATERIAL`
- `LOW_EXTRACTION_CONFIDENCE`
- `SOURCE_CONFLICT`
- `INSUFFICIENT_CORROBORATION`

This is preferable to a plausible but unsupported value.

## 12. Observability

For every candidate considered, log a compact decision trace:

```text
CANDIDATE url=...
PAGE_TYPE=PRODUCT confidence=0.93
IDENTITY=EXACT reason=MPN_MATCH
AUTHORITY=retailer confidence=0.78
EVIDENCE_ALLOWED=YES
```

Rejected example:

```text
CANDIDATE url=...
PAGE_TYPE=CATEGORY confidence=0.96
IDENTITY=COMPATIBLE reason=REQUESTED_MPN_PRESENT_IN_PRODUCT_CARD
EVIDENCE_ALLOWED=NO reason=PAGE_TYPE_NOT_MATERIAL
```

Conflict example:

```text
IDENTITY=CONFLICT requested=ARMOR22 observed=ARMOR26ULTRA
EVIDENCE_ALLOWED=NO
```

The final run summary should count:

- candidates discovered
- candidates rejected by page type
- candidates rejected by identity
- candidates rejected by authority/evidence policy
- validated material sources
- conflicts
- fields accepted
- fields left empty

## 13. Testing strategy

### Unit/TDD coverage

Create focused tests for:

- category page containing target product card does not become product evidence
- official update page does not populate product specifications
- hostname containing brand token does not automatically become manufacturer
- exact requested model vs different observed model produces `CONFLICT`
- exact MPN/GTIN product page passes
- exact technical PDF passes
- retailer exact product page can contribute lower-authority evidence
- conflicting high-confidence sources leave field empty
- telemetry/page-state keys are rejected as product specs
- input identity cannot mask contradictory page identity

### Regression corpus

Preserve the six observed benchmark cases as regression fixtures where legally/practically possible, but write assertions around generalized behavior rather than brand names.

### Live benchmark — OCR/Mistral OFF

Run at least 10 products from 10 brands across multiple categories, for example:

- audio
- mouse/peripheral
- cable/accessory
- smartphone
- laptop
- rugged phone
- storage
- networking
- monitor/display
- printer/accessory or another materially different category

The benchmark must execute the real `scrape_item()` path with:

```text
WEB=ON
PDF=ON
OCR=OFF
MISTRAL=OFF
```

## 14. Acceptance criteria

The next implementation is not considered successful merely because `products_scraped` is high.

Required gates:

1. **Cross-product contamination: 0 known cases** in the benchmark.
2. **False manufacturer classification: 0 known cases** in the benchmark.
3. Category/update/legal/search pages contribute **0 material technical fields**.
4. Exact manufacturer/product/document evidence remains usable.
5. At least 80% of benchmark products produce some validated material evidence **or** a precise fail-closed reason; no generic silent failure.
6. No OCR.space call and no Mistral call during baseline benchmark.
7. Existing full regression suite remains green.
8. Runtime remains bounded: no unbounded retries/crawling; per-product timeout/research budget must remain explicit.

A lower field-completion rate is acceptable if precision increases and unsupported fields are correctly left empty.

## 15. Implementation boundaries

Prefer small modules with clear interfaces rather than growing `batch.py` further. Proposed boundaries:

- `page_type.py` — page/document classification
- `identity_gate.py` — strong identifier/model assessment
- `source_authority.py` — authority classification
- `evidence_policy.py` — permission/threshold/consensus decisions
- existing extraction modules remain responsible for extracting candidates
- `batch.py` orchestrates, but does not own the classification algorithms

If a module with equivalent responsibility already exists, extend it instead of duplicating it.

## 16. Rollout

1. Implement gates behind the existing scraping pipeline without changing UI semantics.
2. Run unit/regression tests.
3. Run the 10-brand live baseline with OCR/Mistral OFF.
4. Compare against the prior six-brand benchmark.
5. Only after source/identity quality is stable, evaluate the incremental value of OCR and Mistral.

## 17. Definition of done

Done means the scraper can say **"I do not know"** safely.

A record is trustworthy when every populated material field can answer:

- Which exact product source produced it?
- Why was that source considered the same product?
- What type of page/document was it?
- What authority class did it have?
- Why was this particular fact accepted?

If those questions cannot be answered, the value must not be auto-filled.
