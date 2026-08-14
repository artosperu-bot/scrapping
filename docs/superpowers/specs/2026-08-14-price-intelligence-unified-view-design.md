# Unified Price Intelligence View — Design

## Goal
Make Price Intelligence self-contained and understandable even when no offers are found, while increasing price discovery breadth without weakening identity validation.

## UX
Keep the existing product selector, actions and progress block at the top. Below it, use an internal notebook with three tabs:

1. **Ofertas** — every validated offer found for the selected run/product; do not stop at the cheapest or first two offers.
2. **Cobertura** — all target channels, including `FOUND`, `NO_HAY` and `ERROR`; a zero-result run must still show every checked channel.
3. **Auditoría** — price-specific execution events (time/stage/source/status/detail) inside the same Price Intelligence module.

The summary must explicitly distinguish `0 ofertas válidas` from execution failure.

## Discovery strategy
Identity priority remains Part Number/MPN, then EAN/UPC/GTIN, then model/name. Keep existing structured-source, targeted-marketplace, Peru-retail and generic-web source families. Increase the desktop source budget from the accidental low value of 12 to the workflow default of 48 so source-family interleaving can actually work. Preserve all offers that pass dedupe, Peru validation, confidence and market-outlier filtering.

Do not weaken strict marketplace validation and do not treat a search-result snippet as a trusted price.

## Coverage and audit
Coverage comes from the same validated run result and must always be rendered. Price-specific audit events are captured locally by the Price module while still flowing through existing global audit behavior if applicable.

## Error handling
Per-source failures remain local. A single marketplace error does not fail the whole run. Terminal UI status is `DONE` when the run completes even with zero offers; fatal orchestration exceptions remain `ERROR`.

## Verification
Add TDD contracts for unified internal tabs, zero-result coverage rendering, all-valid-offers preservation, source budget 48, and no regression to price identity/quality filtering. Run the complete suite and Windows release gate before publishing v0.10.15.
