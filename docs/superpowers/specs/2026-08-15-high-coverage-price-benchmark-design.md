# High-Coverage Price Acquisition Benchmark Design

## Goal
Find the price-acquisition strategy that returns the largest number of valid Peru offers for one explicit product identity, without OCR or Mistral and without relaxing existing identity or price quality gates.

## Baseline
JBL Quantum 350 Wireless / MPN JBLQ350WLBLKAM.
Measured baseline: structured=1 offer/1.68s, directed=3/102.68s, retail=7/15.27s, full=8/276.63s.

## Candidate strategies
- `retail48`: expand the winning general-retail discovery from 24 to 48 candidates and crawl candidates concurrently.
- `hybrid`: run general retail discovery and targeted marketplace discovery concurrently, combine them with structured API offers, deduplicate URLs early, and crawl in parallel.
- `exhaustive`: combine expanded retail, expanded targeted marketplace discovery, generic Peru discovery, and structured APIs; deduplicate and crawl up to 120 unique URLs concurrently.

## Quality constraints
Existing `_is_trusted_final_offer`, Peru-only filtering, identity scoring, deduplication, and market-outlier filtering remain unchanged. Strict marketplace generic HTML offers remain rejected. OCR and Mistral stay disabled.

## Winner rule
Primary metric: number of validated offers. Secondary metric: exact-identifier offer count. Time is only a tiebreaker after coverage and identity quality.

## Production gate
This benchmark is temporary. Do not merge the benchmark harness as production behavior. Only after a winner is measured should its general strategy be implemented in production with TDD and regression tests.
