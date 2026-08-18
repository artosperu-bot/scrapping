# Universal Product Identity + Maximum Recall Price Discovery Perú — Implementation Plan

**Date:** 2026-08-18
**Base:** `release/windows`
**Scope:** Productive implementation P0→P6 from the approved specification. No `main`, no release, no merge, no version bump.

## Frozen baseline

`ProductIdentity(mpn="SA400S37/960G")`

- queries: 58
- raw results: 634
- raw unique URLs: 393
- admitted URLs: 29
- price candidates: 16
- accepted offers: 11
- benchmark sources confirmed: 23
- benchmark sources accepted: 5
- missed sources: 18
- FALSE_NO_HAY: 78.3%
- discovery/query/ranking loss family: 72.2%

The BEFORE artifacts are immutable and must not be overwritten.

## Design constraints

- Universal behavior only; no Kingston/A400/known UPC/benchmark URL production hardcoding.
- Preserve public entrypoints and existing successful adapters.
- Prefer backward-compatible additions.
- Precision over inflated recall.
- No CAPTCHA/security-control bypass.
- Source-specific failures must not collapse to `NO_HAY`.
- Every productive change follows RED → GREEN → regression evidence.

## Task 1 — P0 Telemetry and coverage semantics

**Files:**
- Add `src/product_intelligence/price_trace.py`
- Modify `src/product_intelligence/price_workflow.py`
- Modify `src/product_intelligence/price_channel_registry.py` only if necessary for compatibility
- Add `tests/test_price_trace_coverage.py`

**Behavior:**
- Introduce normalized stage/status events: NOT_SEARCHED, QUERY_EXECUTED_NO_RESULT, RAW_RESULT_FOUND, URL_DISCOVERED, URL_REJECTED_BY_RANKING, URL_REJECTED_BY_DOMAIN, FETCH_STARTED, FETCH_OK, FETCH_BLOCKED, FETCH_TIMEOUT, PARSER_STARTED, PARSER_ZERO_OFFERS, IDENTITY_REJECTED, IDENTITY_ACCEPTED, PRICE_NOT_FOUND, PRICE_REJECTED, OUT_OF_STOCK, OFFER_ACCEPTED, OFFER_DEDUPED.
- Preserve the last real source state independently of final offer count.
- Existing event consumers remain compatible.

**Verification:** focused coverage tests + existing price tests.

## Task 2 — P1 Identifier schema and identity hardening

**Files:**
- Modify `src/product_intelligence/identifiers.py`
- Modify `src/product_intelligence/identity_bootstrap.py`
- Modify `src/product_intelligence/price_discovery.py`
- Modify `src/product_intelligence/price_adapters.py` only where identifier typing is ambiguous
- Add/extend identity tests.

**Behavior:**
- Generic/category/product-type/navigation text cannot become a high-confidence brand.
- Separate MPN/SKU/GTIN/UPC/EAN semantics.
- Remove SKU→GTIN, MPN→GTIN, marketplace-id→GTIN fallbacks.
- Treat null/none/N/A textual sentinels as empty identifiers.
- Validate GTIN/UPC/EAN length, digits and check digit where applicable while preserving leading zeros.
- Add safe MPN canonical key + separator aliases without overwriting original.

**Verification:** negative identity tests, identifier contamination tests, existing identity benchmark tests.

## Task 3 — P1.5 Canonical identity integration with Price

**Files:**
- Reuse/extend `identity_refinement.py` / `identity_bootstrap.py`; add a small price bridge only if necessary.
- Modify `price_workflow.py` minimally at the entry boundary.
- Tests for MPN-only, UPC-only, EAN-only, brand+model and unresolved fallback.

**Behavior:**
- Resolve partial identity before discovery when safe.
- Preserve original input and evidence/provenance.
- Never require full identity; continue with available verified signals.
- Resolver failure must degrade gracefully to the original identity.

## Task 4 — P2 Query expansion + domain-aware ranking

**Files:**
- Modify `discovery.py`
- Modify `price_discovery.py`
- Modify `price_peru_coverage.py`
- Add `tests/test_price_query_recall.py`.

**Behavior:**
- Query signal set: original identifier, compact/separator aliases, verified brand+identifier, verified GTIN/UPC/EAN, verified brand+model.
- Case variants do not consume extra budget.
- Directed `site:X` searches enforce domain before/during ranking; in-domain PDP cannot be displaced by another domain.
- Track query information gain: raw results, accepted in-domain, new URLs/domains/sellers/listings.

## Task 5 — P2.5 Open Peru discovery + capability memory

**Files:**
- Reuse `capabilities.py` and existing history/workspace paths; add price source capability storage only if required.
- Modify `price_peru_coverage.py`.
- Tests for new `.pe`/`.com.pe` ecommerce domains discovered without hardcoded retailer names.

**Behavior:**
- Two lanes: known sources + open Peru discovery.
- Open discovery admits identity-valid PDP-like Peru ecommerce candidates beyond static hints.
- Persist observed source/platform/extraction capabilities with timestamp; observations are hints, never permanent truth.

## Task 6 — P3 Novelty-based stopping

**Files:**
- Modify `price_peru_coverage.py` and targeted discovery as needed.
- Add premature-stop tests.

**Behavior:**
- Remove `first found => break` semantics.
- Continue while queries produce novel PDPs/listings/sellers and budget remains.
- Stop on limit, exhausted budget, definitive source unavailability, or bounded consecutive no-novelty.

## Task 7 — P4 Marketplace expansion

**Files:**
- Reuse `marketplace_mapper.py`, `marketplace_resolution.py`, `price_adapters.py`, `price_workflow.py`.
- Add marketplace expansion tests.

**Behavior:**
- Preserve catalog product vs listing/publication vs seller vs offer identities.
- Mercado Libre: use API/catalog/listing information when authorized and available; multiple sellers/offers when exposed.
- Falabella/Ripley/Sodimac-family: extract multiple publications/sellers when public structured data exposes them.
- No benchmark-specific seeds.

## Task 8 — P5 Access + parser cascade; P5.5 price quality/dedupe

**Files:**
- Modify `mercadolibre_oauth.py` only to make secure credential fallback robust.
- Modify `price_workflow.py`, `price_discovery.py`, adapters/parsers as demonstrated by tests.
- Add access/parser/price semantics tests.

**Behavior:**
- Access failure is distinct from parser failure.
- ML credential unavailability emits `ML_API_AUTH_FAILED` and discovery continues; no secrets logged.
- Parser cascade: public API/catalog → embedded structured JSON → JSON-LD → HTML → render when justified.
- Distinguish product selling price from unit/installment/shipping/coupon/reference prices.
- Preserve out-of-stock evidence and product condition.
- Improve dedupe using publication/listing/seller/canonical URL semantics without collapsing genuine seller offers.

## Task 9 — P6 AFTER + universality regression

**Files:**
- Add QA-only AFTER harness/workflow and artifacts, separate from frozen BEFORE.
- Add universality fixture/matrix.

**AFTER input:** exactly `ProductIdentity(mpn="SA400S37/960G")`; no injected brand/model/UPC/URLs/sellers.

**Artifacts:**
- `after_sa400s37_960g.json`
- `before_after_comparison.json`
- `coverage_after.json`
- `identity_after.json`
- `query_information_gain.json`
- `source_capabilities.json`
- `universality_matrix.json`

**Gates:**
- brand must not resolve to category/noise text.
- SKU→GTIN contamination = 0; marketplaceID→GTIN = 0; textual-null GTIN = 0.
- known false-positive price = 0.
- benchmark discovery target >=90% when public evidence is technically reachable; otherwise each exception classified.
- accepted offers materially improve only if supported by valid evidence.
- universality: computing, audio, smartphone/electronics, appliance/tool/general retail, non-electronic; MPN-only, UPC-only, EAN-only, brand+model.
- focused tests, price tests, existing QA, full regression, Windows build when applicable.

## Final stop

Do not merge or release. Deliver evidence-only implementation report and leave the development PR in draft/reviewable state.
