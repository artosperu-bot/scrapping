# Identity Bootstrap Recall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve recall for unknown-brand product inputs by resolving brand/model from real search-result and page-content evidence before deep scraping, without weakening fail-closed validation.

**Architecture:** Keep the existing precision-first validation gates untouched. Add a bounded identity-bootstrap layer that first collects exact-search candidates, then probes only the strongest candidates with lightweight HTML fetches, extracts structured/visible identity signals, aggregates brand/model evidence across independent hosts, resolves only with a decisive score, and then expands deep search using the learned identity. Discovery remains permissive; validation remains strict.

**Tech Stack:** Python 3.12, requests/BeautifulSoup, existing `web_fetch`, `html_extract`, `source_signals`, pytest, GitHub Actions.

## Global Constraints

- No hardcoded product→brand or product→domain mappings.
- Preserve `FAIL_CLOSED`.
- Preserve zero cross-product contamination, zero false manufacturers, zero non-material evidence.
- OCR and Mistral must remain unused when disabled.
- `main` is untouched; work stays on `feat/source-validation-gates-universal` targeting `release/windows`.
- Use bounded candidate/page probing and early success; do not add indiscriminate retries or longer timeouts.

---

### Task 1: Page-backed identity candidate extraction

**Files:**
- Modify: `src/product_intelligence/identity_bootstrap.py`
- Test: `tests/test_identity_bootstrap.py`

**Interfaces:**
- Consumes: `SearchCandidate`, `ProductIdentity`, existing `fetch_page`, `extract_page`, `derive_observed_identity`.
- Produces: page-backed identity signals used by `resolve_identity_from_candidates` and bootstrap telemetry.

- [ ] **Step 1: Write failing tests** proving that a candidate whose SERP title does not expose the brand can still resolve brand from structured page content, while a conflicting page cannot.
- [ ] **Step 2: Verify RED** with `pytest tests/test_identity_bootstrap.py -q`.
- [ ] **Step 3: Implement bounded candidate probing** with browser fallback disabled, canonical URL dedupe, material response checks, and extraction of observed brand/model/product_name/strong identifiers from page content.
- [ ] **Step 4: Merge SERP and page signals** without allowing hostname similarity alone to establish manufacturer truth.
- [ ] **Step 5: Verify GREEN** with focused tests and full regression.

### Task 2: General cross-source identity scoring

**Files:**
- Modify: `src/product_intelligence/identity_bootstrap.py`
- Test: `tests/test_identity_bootstrap.py`

**Interfaces:**
- Consumes: SERP evidence and page-backed evidence grouped by canonical host.
- Produces: `IdentityBootstrapResult(status, identity, confidence, reason, official_domain_hint, brand_scores, brand_hosts)`.

- [ ] **Step 1: Add failing tests** for brand-before-model, suffix/prefix title layouts, independent-host reinforcement, retailer down-weighting, and tied brands remaining unresolved.
- [ ] **Step 2: Verify RED**.
- [ ] **Step 3: Implement generic scoring** where explicit structured brand/manufacturer and exact strong-ID co-occurrence outweigh title frequency; independent hosts add confidence; marketplaces are weaker; conflicts penalize heavily.
- [ ] **Step 4: Resolve model only from observed content or preserve raw descriptive model; never infer sibling variants.
- [ ] **Step 5: Verify GREEN**.

### Task 3: Adaptive search and performance budget

**Files:**
- Modify: `src/product_intelligence/discovery.py`
- Modify: `src/product_intelligence/identity_bootstrap.py`
- Test: `tests/test_identity_bootstrap.py`

**Interfaces:**
- Consumes: resolved identity and optional official-domain hint.
- Produces: bounded adaptive deep-query sequence and early success.

- [ ] **Step 1: Add failing tests** that deep queries do not add a brand before resolution and do add it after resolution.
- [ ] **Step 2: Verify RED**.
- [ ] **Step 3: Limit bootstrap to high-value queries and top candidate probes; dedupe query, canonical URL, and host; stop as soon as identity is decisively resolved.
- [ ] **Step 4: Keep no-early-fail behavior**: unresolved bootstrap falls back to generic discovery rather than declaring failure.
- [ ] **Step 5: Verify GREEN and full CI**.

### Task 4: Real unknown-brand benchmark and telemetry

**Files:**
- Modify: `tests/integration_identity_resolution_benchmark.py`
- Modify: `.github/workflows/identity-resolution-benchmark.yml`

**Interfaces:**
- Inputs: `Armor 22`, `A2794`, `SM-S928B`, `910-006556`, `JBLT530CBLKAM`, `V15 G4 IRU` with no supplied brand.
- Outputs: identity discovery telemetry, source-validation metrics, elapsed time, final status.

- [ ] **Step 1: Extend telemetry** with top candidate previews, page probes attempted/succeeded, observed brand/model signals, rejection reasons, and query counts.
- [ ] **Step 2: Run six-case benchmark** with WEB=ON, PDF=ON, OCR=OFF, MISTRAL=OFF.
- [ ] **Step 3: Require** zero false manufacturer, zero contamination, zero non-material evidence, zero forbidden provider events, and materially improved identity-resolution/coverage over the 0/6 baseline.
- [ ] **Step 4: If a case remains unresolved, use its telemetry to fix the generic resolver rather than add a product exception.
- [ ] **Step 5: Run existing source-validation six-case and ten-brand benchmarks to prove protections remain intact.

### Task 5: Release gate

**Files:**
- No production version bump until all gates pass.

- [ ] **Step 1: Confirm full CI and PDF smoke green.**
- [ ] **Step 2: Confirm identity benchmark materially improved and source-validation benchmarks pass.**
- [ ] **Step 3: Merge only to `release/windows` after verification; never touch `main`.**
- [ ] **Step 4: Build/publish the next Windows release only after integration with the UI/workspace PR and verify the public release asset.**
