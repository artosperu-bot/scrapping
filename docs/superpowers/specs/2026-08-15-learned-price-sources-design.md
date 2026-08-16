# Learned Price Sources Design

## Goal
Increase price coverage and reduce repeated discovery time by remembering only previously validated product-detail URLs and revalidating them on future runs.

## Evidence
For JBL Quantum 350 Wireless / `JBLQ350WLBLKAM`, the current full pipeline produced 8 validated offers in 276.63s. A benchmark that revalidated previously discovered strong PDPs plus fresh retail discovery produced 11 current offers in 12.31s; excluding the single `PROBABLE_MODEL` row still left 10 strong offers.

## Architecture
Persist a dedicated `price_intelligence/source_bindings.json` keyed by the strongest explicit product identifier (`mpn`, `ean`, `upc`, `gtin`, then model/product name). A binding stores URL, channel, identity match, and last-seen metadata, but never acts as a cached current price.

Only offers whose identity match is `EXACT_*` or `BRAND_MODEL` may teach the registry. `PROBABLE_MODEL` and weaker evidence may still be returned if the existing current-run gates accept them, but they must never become learned bindings.

### Cold path
When no learned sources exist for the product, preserve the current full discovery workflow. After normal validation, persist strong source bindings from the valid offers.

### Warm path
When learned sources exist:
1. Revalidate learned PDPs live.
2. Run fresh general-Peru retail discovery and structured API sources concurrently where safe.
3. Deduplicate URLs and current offers.
4. Keep the existing Peru, confidence, strict marketplace, identity, and outlier gates unchanged.
5. Persist any newly validated strong PDPs.
6. If warm-path coverage is materially weak, fall back to the existing full discovery path rather than returning stale or incomplete cached data.

Static/API refresh may be concurrent. Browser fallback is controlled/sequential to avoid the coverage regressions observed when multiple Playwright sessions were run concurrently.

## Safety and correctness
- Never return a stored old price merely because its URL is remembered.
- Every learned URL is fetched and revalidated during the current run.
- Product identities are isolated; a binding learned for one MPN cannot be loaded for another.
- Malformed/missing registry data fails closed to an empty learned-source set.
- No product, brand, retailer, or URL is hardcoded in production logic.

## Success criteria
- Unit tests prove strong-only persistence, product isolation, dedupe, and malformed-file safety.
- Workflow tests prove warm-path use, fresh revalidation, fallback behavior, and source learning.
- Existing price tests and full CI remain green.
- A live explicit-model smoke demonstrates that the production implementation retains or improves coverage without weakening identity gates.
