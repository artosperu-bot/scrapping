# High-Coverage Price Acquisition Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether expanded/concurrent price acquisition can beat the existing 8-offer full baseline while preserving identity quality.

**Architecture:** Keep production modules unchanged during the experiment. Extend only the temporary benchmark harness with three candidate strategies that reuse existing discovery, extraction, identity, Peru, dedupe, and outlier gates. Run candidates as separate GitHub Actions matrix jobs and compare artifacts.

**Tech Stack:** Python 3.12, requests, Playwright, GitHub Actions, existing product_intelligence price modules.

## Global Constraints
- Product identity fixed to JBL Quantum 350 Wireless / JBLQ350WLBLKAM for apples-to-apples measurement.
- OCR disabled.
- Mistral disabled.
- No relaxation of `_is_trusted_final_offer` or identity matching.
- Benchmark branch only; no production merge from the experiment itself.
- Winner = most validated offers; exact-ID count breaks quality ties; elapsed time breaks remaining ties.

---

### Task 1: Add expanded benchmark candidates

**Files:**
- Modify: `scripts/benchmark_price_methods_q350.py`
- Modify: `.github/workflows/price-integration-smoke.yml`

**Interfaces:**
- Consumes: `discover_general_peru_retailers`, `discover_additional_peru_pdps`, `discover_price_sources`, `_try_vtex`, `_try_mercadolibre`, `_parse_page_with_dynamic_retry`, `_try_shopify`.
- Produces: `price_method_benchmark/<method>/result.json` for `retail48`, `hybrid`, and `exhaustive`.

- [ ] Run `retail48`: discover up to 48 general-retail candidates and crawl up to 10 candidates concurrently.
- [ ] Run `hybrid`: execute retail and targeted discovery concurrently, merge/dedupe candidates, run structured APIs concurrently with web crawl, then apply unchanged quality gates.
- [ ] Run `exhaustive`: combine retail(80), targeted(10/domain), generic(64), structured APIs, dedupe up to 120 URLs, and crawl with up to 12 workers.
- [ ] Record elapsed seconds, validated offers, channels, exact-identifier count, and individual offer evidence in each artifact.
- [ ] Configure the benchmark workflow to run only these three new methods so previous baselines are not repeated.

### Task 2: Select the measured winner

**Files:**
- Read artifacts only; no production edits.

**Interfaces:**
- Consumes: three `result.json` artifacts plus baseline measurements.
- Produces: winner decision and production implementation requirements.

- [ ] Compare validated offer count against baseline full=8 and retail=7.
- [ ] Reject any candidate that increases coverage by accepting ambiguous/wrong identity evidence.
- [ ] Prefer highest validated-offer count; use exact-ID count and elapsed time as tie breakers.
- [ ] If no candidate beats 8, retain the most efficient strategy and document uncovered channels rather than weakening gates.

### Task 3: Productionize only the winner

**Files:**
- To be selected after benchmark evidence; expected primary file: `src/product_intelligence/price_workflow.py`.
- Tests: existing/new `tests/test_price_*.py`.

**Interfaces:**
- Consumes: measured winner behavior.
- Produces: general production strategy without JBL-specific hardcoding.

- [ ] Write failing unit/regression tests for concurrency, URL dedupe, unchanged identity gates, and deterministic output.
- [ ] Verify tests fail before production implementation.
- [ ] Implement only the measured winning architecture generically.
- [ ] Run focused price tests, full CI, and one live explicit-model smoke before considering merge.
