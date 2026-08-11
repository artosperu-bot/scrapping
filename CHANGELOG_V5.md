# V5 — Marketplace mapping refinements

General improvements focused on three marketplace fields without adding brand- or product-specific rules.

## NameEn
- `NameEn` is now explicitly classified as `DERIVABLE`.
- Reuses a verified English/technical product name when available.
- Otherwise builds a conservative logistics title from verified brand/model/variant attributes.
- Does not invent marketing claims or translate technical tokens.

## Variation
- `Variación` is now explicitly classified as `DERIVABLE`.
- Priority: explicit variant > explicit color > capacity tied to an exact product identity.
- Capacity is not used as a variation when identity is weak/ambiguous.
- If variation cannot be proven, the cell stays empty.

## Images
- Auto-fill still accepts only `EXACT_VARIANT` or `EXACT_PRODUCT` media.
- `EXACT_VARIANT` always outranks `EXACT_PRODUCT`.
- Strong MPN/EAN/GTIN/capacity evidence and variant-selection provenance increase ranking.
- Structured `Product.image`, OpenGraph, zoom/large and srcset sources are preferred over generic DOM assets within the same identity scope.
- Family/unverified images remain excluded from automatic Excel population.

## Principle
The marketplace template never weakens product truth: if identity or variation is not supported by evidence, the field remains empty.
