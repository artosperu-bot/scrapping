# Learned Price Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist strong product-to-PDP bindings and use them as live-revalidated warm sources to increase price coverage and reduce repeated discovery time.

**Architecture:** Add a dedicated source-binding registry in `price_history.py`. `price_workflow.py` keeps the current full workflow as the cold/fallback path, but uses learned strong URLs plus fresh retail/API discovery on warm runs. Stored URLs are hints only; all prices must be re-fetched and pass current validation gates.

**Tech Stack:** Python 3.12, requests, Playwright, JSON persistence, pytest.

## Global Constraints
- No JBL, retailer, or product URL hardcoding in production.
- Learn only `EXACT_*` and `BRAND_MODEL` bindings.
- Never return cached stale price values.
- Existing Peru, confidence, strict-marketplace, identity and outlier gates remain unchanged.
- Browser fallback must not run concurrently.
- Missing/corrupt source registry fails closed.

---

### Task 1: Source binding registry

**Files:**
- Modify: `src/product_intelligence/price_history.py`
- Create: `tests/test_price_source_memory.py`

**Interfaces:**
- Produces: `load_validated_source_urls(output_root, identity) -> list[str]`
- Produces: `save_validated_source_bindings(output_root, identity, offers) -> None`

- [ ] Write failing tests for strong-only learning, `PROBABLE_MODEL` exclusion, product isolation, URL dedupe, and corrupt JSON.
- [ ] Run focused tests and verify RED.
- [ ] Implement minimal atomic JSON registry.
- [ ] Run focused tests and verify GREEN.

### Task 2: Warm-path live revalidation

**Files:**
- Modify: `src/product_intelligence/price_workflow.py`
- Modify/Create tests around `tests/test_price_workflow.py` or `tests/test_price_source_memory.py`

**Interfaces:**
- Consumes: learned URLs from Task 1.
- Produces: live `PriceOffer` rows only after current-page extraction and existing gates.

- [ ] Write failing tests proving a learned URL is re-fetched, not returned stale.
- [ ] Write failing test proving warm path avoids expensive generic/targeted discovery when learned coverage is healthy.
- [ ] Write failing test proving weak warm results fall back to current full discovery.
- [ ] Implement static/API learned refresh with bounded concurrency and sequential browser fallback.
- [ ] Merge learned + fresh retail + structured offers and keep existing final gates.
- [ ] Save newly validated strong bindings after every successful run.
- [ ] Run focused price tests.

### Task 3: Regression and live verification

**Files:**
- No additional production files unless tests expose a root cause.

- [ ] Run all price-related unit tests.
- [ ] Run full CI.
- [ ] Run one live explicit-model price smoke with OCR/Mistral disabled.
- [ ] Compare coverage, exact-identity count, and elapsed time with baseline full=8/276.63s and benchmark learned=11/12.31s.
- [ ] Merge only if quality gates remain intact.
