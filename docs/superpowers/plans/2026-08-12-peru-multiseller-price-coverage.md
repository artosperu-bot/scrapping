# Peru multiseller price coverage implementation plan

## Goal

Make Price Intelligence return the maximum set of validated Peru-only offers for an exact product identity, preserving multiple sellers/publications per marketplace.

## Rules

- Peru only in the final offer set.
- Structured/direct probes first: MercadoLibre MPE plus VTEX-compatible Peru storefronts.
- Targeted PDP discovery for Falabella, Ripley, Sodimac and official brand stores.
- Keep multiple sellers and multiple publication IDs/SKUs for the same exact product.
- Never dedupe an entire channel to one offer.
- Exact MPN alone is insufficient if title/model has a contradictory product generation.
- Category/search pages never count as offers.
- Ambiguous coupon/marketing amounts never become product prices.
- Generic web discovery is additive fallback only.

## Verification

1. RED tests for Falabella direct probe, strict MPN/model conflict, Peru-only output and multiseller VTEX.
2. GREEN full regression.
3. Live price smoke for JBLQ350WLBLKAM and existing JBL fixtures.
4. Inspect actual Q350 offers, not only workflow status.
5. Merge only after CI + live smoke success.
6. Build and verify the Windows artifact on the merge commit.
