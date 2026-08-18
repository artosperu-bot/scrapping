# Universal Product Identity + Maximum Recall Price Discovery Peru

## Baseline

Frozen BEFORE: `ProductIdentity(mpn="SA400S37/960G")` only. 58 queries, 634 raw results, 393 raw unique URLs, 29 admitted URLs, 16 price candidates, 11 accepted offers, 18/23 confirmed benchmark sources missed, FALSE_NO_HAY 78.3%, discovery/query/ranking 72.2% of terminal misses. BEFORE artifact is immutable and is not used as productive seed input.

## Guardrails

- Branch only: `feat/universal-price-intelligence` from `release/windows`.
- Never modify `main`, publish a release, merge, or bump the final version in this work.
- No Kingston/A400/UPC/benchmark-store special case in productive logic.
- Preserve OCR, Mistral, PDF, Multimedia, Excel, updater, existing Price Intelligence and existing Mercado Libre behavior unless changed by a backwards-compatible tested fix.
- Oracle data is QA-only and evaluated after a run.
- TDD: failing focused test before each productive behavior change.

## P0 — Telemetry and coverage semantics

1. Add a small price trace/coverage state model with ordered terminal observations.
2. Emit normalized stages for query, raw result, ranking/domain rejection, URL admission, fetch, parser, identity, price, stock, accepted/deduped offers.
3. Build channel coverage from observations plus accepted offers. Never collapse zero final offers to `NO_HAY`; preserve last demonstrated stage.
4. Keep old output fields where possible and add fields backwards-compatibly.

## P1 — Identity hardening

1. Harden `identity_bootstrap.py` against category/product/navigation/noise labels becoming brands.
2. Require stronger evidence for high-confidence brand resolution and prevent category phrases from cross-source SERP dominance.
3. Reuse identifier validation in `identifiers.py`; add safe empty-value handling and identifier aliases without conflating types.
4. Remove every SKU/MPN/marketplace-id fallback into GTIN evidence.
5. Harvest only explicit validated GTIN/EAN/UPC page evidence with provenance when present.

## P1.5 — Identity integration with Price

1. Resolve partial identity once before price discovery with bounded fallback.
2. Continue with original signals when identity cannot be safely resolved.
3. Emit input identity and resolved identity separately so audit remains truthful.
4. Avoid a second hidden bootstrap after a safe resolution attempt.

## P2 — Query expansion and domain-aware ranking

1. Add safe identifier aliases: original, compact, separator variants, case-normalized key while preserving the original.
2. Generate progressive queries from verified signals only.
3. Add optional/inferred domain constraint to directed `site:X` searches before ranking.
4. Record per-query raw results, valid in-domain results, new URLs/domains/listings/sellers and stop reason.
5. Maintain bounded budgets and avoid redundant case-only queries.

## P2.5 — Open Peru discovery + capability memory

1. Keep known-source lane.
2. Add/open generic Peru ecommerce lane using identity signals, not benchmark domains.
3. Detect platform capabilities (VTEX, Shopify, WooCommerce/Magento hints, JSON-LD, custom) from observed pages/endpoints.
4. Persist source capability observations with timestamps and non-eternal confidence/TTL semantics.

## P3 — Novelty-based stopping

1. Replace `if found: break` in target-domain discovery with bounded novelty logic.
2. Continue query variants while new PDPs/listings are still produced and budget remains.
3. Stop on saturation/budget/source-unavailable, not first hit.

## P4 — Marketplace expansion

1. Reuse existing Mercado Libre API/OAuth and adapters; classify auth failures without aborting the rest of Price.
2. Preserve catalog/product/listing/seller/publication identifiers separately.
3. Expand multiple marketplace offers where public structured data exposes them.
4. Reuse platform adapters before site-specific HTML.

## P5/P5.5 — Access, parser, price semantics and dedupe

1. Separate access result from parser result in telemetry.
2. Cascade structured/platform/API -> JSON-LD/embedded -> HTML -> render when justified.
3. Fix JSON-LD identifier contamination and empty identifier values.
4. Strengthen price semantics so incidental small numbers/unit/installment/shipping values cannot become selling price.
5. Preserve out-of-stock coverage and condition.
6. Improve dedupe with publication/listing/seller identifiers while preserving genuinely distinct offers.

## P6 — Verification and AFTER

1. Focused tests for P0-P5.
2. Existing Price Intelligence tests.
3. Full regression.
4. Live AFTER with exactly `ProductIdentity(mpn="SA400S37/960G")` and no injected brand/model/UPC/EAN/GTIN/URLs/sellers.
5. Generate separate AFTER artifacts and BEFORE->AFTER comparison.
6. Evaluate 23-source QA oracle only after the run.
7. Run universality matrix: computing, audio, smartphone/electronics, appliance/tool/general retail, non-electronic; cover MPN-only, UPC-only, EAN-only and brand+model.
8. Run Windows build when branch state is otherwise verified.
9. Report only demonstrated metrics, remaining blockers and performance cost.
