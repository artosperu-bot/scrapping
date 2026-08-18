# Smart Evidence Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the current implicit `batch.py` coordination into an explicit field-level Product Evidence Orchestrator that reuses the existing PDF/WEB/Excel engines, maximizes verified field coverage, fails closed on product/variant conflicts, and is exercised by the real Windows desktop pipeline.

**Architecture:** Keep the current `ProductPipeline`, PDF preflight/matcher, `resolution_engine`, template analysis, evidence policy, final write barrier, WEB discovery, PDF Review and desktop chain. Add focused orchestration units above them: a shared field evidence view, a field-resolution planner, a generic source router and a stateful orchestrator. `batch.py` becomes an adapter that feeds accepted records to the orchestrator, asks it for the next useful source intent, and stops when coverage/budget/conflict rules say so.

**Tech Stack:** Python 3.12, Pydantic models, dataclasses, existing Product Intelligence modules, pytest, Tkinter desktop shell, PyInstaller Windows workflow.

**Spec:** User-supplied `PROMPT MAESTRO DEFINITIVO — PRODUCT INTELLIGENCE SMART EVIDENCE ORCHESTRATOR` attached 2026-08-17.

## Global Constraints

- Preserve PR #63 and previously certified desktop/PDF Review/packaged E2E behavior.
- No brand/MPN/URL hardcoding for JBL or any regression product.
- Contradiction vetoes similarity; UNKNOWN/SIBLING/RELATED/UNRELATED never auto-write fields.
- Reuse `ProductFingerprint`, `ProductDocumentMatcher`, PDF identity preflight, `resolution_engine`, `final_evidence_gate`, current WEB discovery and Excel writer.
- Search ceilings remain 8 queries, 5 candidates/query, 15 pages, 8 PDFs, 5 accepted sources; ceilings are not targets.
- PDF/WEB are specialists; orchestration is field-level and BEST EVIDENCE FIRST.
- No massive crawling, anti-bot bypass, proxy evasion or snippet-as-final-evidence.
- Preserve original input identifiers and monotonic identity.
- Do not merge, release or version-bump until deterministic QA + generalization + live benchmark + packaged `.exe` E2E + BEFORE/AFTER are evidenced.

---

### Task 1: Freeze the productive contracts with orchestrator RED tests

**Files:**
- Create: `tests/test_product_evidence_orchestrator.py`
- Read/reuse: `src/product_intelligence/resolution_engine.py`
- Read/reuse: `src/product_intelligence/template_contract.py`
- Read/reuse: `src/product_intelligence/final_evidence_gate.py`

**Interfaces:**
- Consumes existing `ProductRecord`, `Evidence`, `analyze_resolution()` and `ResolutionBudget`.
- Defines expected public API for later tasks: `ProductEvidenceOrchestrator`, `OrchestratorSnapshot`, `SourceIntent`.

- [ ] **Step 1: Write RED tests for the eight mandatory scenarios**

Create deterministic fixtures that prove:

```python
# 1 PDF resolves all -> EARLY_STOP and no WEB intent
# 2 PDF partial -> only unresolved fields are requested from WEB
# 3 PDF zero + exact identity -> next source is WEB/STRUCTURED, not product failure
# 4 sibling PDF evidence never resolves a field; fallback continues
# 5 sibling WEB evidence never resolves a field
# 6 GTIN routes to structured/manufacturer before PDF
# 7 technical driver routes to official PDF/manufacturer
# 8 already-resolved battery is not included in later field lookup
# 9 unresolved conflicting values are CONFLICTED and non-writable
# 10 budget ceilings remain hard stops
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest -q tests/test_product_evidence_orchestrator.py`
Expected: collection/import failures because the new orchestration modules do not yet exist.

- [ ] **Step 3: Commit the RED contract**

Commit message: `test: define smart evidence orchestrator contract`

---

### Task 2: Add a shared field evidence view without replacing ProductRecord

**Files:**
- Create: `src/product_intelligence/field_evidence_store.py`
- Test: `tests/test_product_evidence_orchestrator.py`

**Interfaces:**
- Produces:
  - `FieldEvidenceEntry(field, value, source_type, authority, source_url, relationship, scope, confidence, evidence)`
  - `FieldEvidenceStore(required_fields)`
  - `FieldEvidenceStore.ingest_record(record)`
  - `FieldEvidenceStore.snapshot(record) -> FieldCoverageSnapshot`
- Reuses `analyze_resolution(record, template_plan_like)` as the authoritative field-state classifier instead of duplicating semantic mapping.

- [ ] **Step 1: Implement the minimal shared store**

The store keeps accepted `Evidence` references and field-level provenance. It must never mutate source evidence to manufacture certainty.

- [ ] **Step 2: Map resolution states**

`FOUND_*`, `NOT_APPLICABLE` and marketplace-option terminal states count as resolved; `INSUFFICIENT_EVIDENCE` counts missing; `CONFLICTING_EVIDENCE` and blocking cross-field issues count conflicted.

- [ ] **Step 3: Verify focused tests**

Run: `python -m pytest -q tests/test_product_evidence_orchestrator.py`
Expected: store-specific assertions pass; planner/router imports remain RED.

- [ ] **Step 4: Commit**

Commit message: `feat: add shared field evidence store`

---

### Task 3: Implement Field Resolution Planner

**Files:**
- Create: `src/product_intelligence/field_resolution_planner.py`
- Reuse: `src/product_intelligence/final_evidence_gate.py`
- Test: `tests/test_product_evidence_orchestrator.py`

**Interfaces:**
- Produces:
  - `FieldPlan(field, field_kind, required_scope, priority, preferred_source_kinds)`
  - `plan_field(field, *, required=True) -> FieldPlan`
  - `plan_fields(fields) -> tuple[FieldPlan, ...]`
- Generic field kinds: `IDENTIFIER`, `SKU_VARIANT`, `TECHNICAL`, `WARRANTY_REGIONAL`, `PACKAGE`, `COMPATIBILITY`, `GENERAL`.

- [ ] **Step 1: Encode field semantics generically**

Use semantic names/keywords and `is_sku_sensitive_field()`; never brand-specific rules.

- [ ] **Step 2: Protect SKU-sensitive fields**

Identifier/color/storage-memory configuration/region/bundle/package contents require `SKU` evidence when semantics demand it.

- [ ] **Step 3: Add field priority**

Use `CORE`, `IMPORTANT`, `OPTIONAL`; required template fields default at least IMPORTANT, identity fields CORE.

- [ ] **Step 4: Run focused tests GREEN for field planning**

- [ ] **Step 5: Commit**

Commit message: `feat: plan evidence resolution per field`

---

### Task 4: Implement generic Best-Evidence Source Router

**Files:**
- Create: `src/product_intelligence/source_router.py`
- Reuse: `src/product_intelligence/source_strategy.py`
- Reuse: `src/product_intelligence/universal_resolution_policy.py`
- Test: `tests/test_product_evidence_orchestrator.py`

**Interfaces:**
- Produces:
  - `SourceIntent(engine, tier, source_kind, fields, required_scope, reason, expected_value)`
  - `route_sources(identity, field_plans, *, category=None, strategy=None, history=()) -> tuple[SourceIntent, ...]`
- Engine values initially map to existing capabilities only: `EXISTING`, `IDENTITY`, `PDF`, `WEB_STRUCTURED`, `WEB_FALLBACK`.

- [ ] **Step 1: Route identifiers to structured/manufacturer paths before PDF**
- [ ] **Step 2: Route technical specs to official PDF/manufacturer first**
- [ ] **Step 3: Route warranty to official regional WEB/support**
- [ ] **Step 4: Route SKU-sensitive/package fields to exact-SKU-capable sources**
- [ ] **Step 5: Add generic category profiles**

Profiles may distinguish consumer electronics, components, printers, smartphones, computers and generic products, but must not hardcode brands.

- [ ] **Step 6: Respect SourceStrategy feature switches**
- [ ] **Step 7: Skip previously blocked/insufficient sources when no expected value remains**
- [ ] **Step 8: Run focused tests GREEN**
- [ ] **Step 9: Commit**

Commit message: `feat: route best evidence per field`

---

### Task 5: Implement Product Evidence Orchestrator state machine

**Files:**
- Create: `src/product_intelligence/product_evidence_orchestrator.py`
- Reuse: `src/product_intelligence/universal_resolution_policy.py`
- Reuse: `src/product_intelligence/evidence_policy.py`
- Test: `tests/test_product_evidence_orchestrator.py`

**Interfaces:**
- Produces:
  - `OrchestratorSnapshot(required_fields, resolved_fields, missing_fields, conflicted_fields, source_history, early_stop, stop_reason, next_intents)`
  - `ProductEvidenceOrchestrator(identity, required_fields, *, category=None, budget=None, source_strategy=None)`
  - `.observe_record(record, *, engine, source_url, status="ACCEPTED") -> OrchestratorSnapshot`
  - `.observe_source_outcome(intent, status, *, reason="") -> OrchestratorSnapshot`
  - `.plan_next() -> OrchestratorSnapshot`
  - `.audit() -> dict`

- [ ] **Step 1: Centralize required/resolved/missing/conflicted state**
- [ ] **Step 2: Use existing `evaluate_next_action()` for global stop/refine/search decisions**
- [ ] **Step 3: Maintain one shared SearchBudgetTracker**
- [ ] **Step 4: Ensure resolved fields are removed from later source intents**
- [ ] **Step 5: Preserve hard conflicts as stop/manual-review conditions**
- [ ] **Step 6: Record source outcomes and expected-value history**
- [ ] **Step 7: Run all orchestrator tests GREEN**
- [ ] **Step 8: Commit**

Commit message: `feat: add product evidence orchestrator`

---

### Task 6: Wire the orchestrator into the productive batch flow

**Files:**
- Modify: `src/product_intelligence/batch.py`
- Test: `tests/test_product_evidence_orchestrator.py`
- Create: `tests/test_smart_orchestrator_batch_integration.py`

**Interfaces:**
- `scrape_item()` creates one `ProductEvidenceOrchestrator` using `template_plan["scrape_semantics"]`.
- Existing WEB/PDF functions remain data-acquisition engines; orchestrator supplies only the fields/intents that remain useful.

- [ ] **Step 1: Write RED integration test**

Prove `batch.scrape_item()` asks WEB only for fields left unresolved after accepted PDF/manufacturer evidence.

- [ ] **Step 2: Replace procedural gap decisions with orchestrator snapshots**

Do not rewrite URL fetching/PDF processing. Keep `_ingest_direct_documents`, `ProductPipeline.process_url`, `search_web`, and `search_web_for_fields` as existing engines.

- [ ] **Step 3: Feed accepted records into shared state**
- [ ] **Step 4: Feed rejected/blocked source outcomes into source history**
- [ ] **Step 5: Persist `smart_orchestrator` audit in `rec.evidence_graph`**

Audit must include required/resolved/missing/conflicted, source intents/outcomes, budget, early-stop reason, PDF/WEB contribution counts.

- [ ] **Step 6: Preserve `resolution_audit` and `resolution_budget` for compatibility**
- [ ] **Step 7: Run focused + batch integration tests**
- [ ] **Step 8: Run full regression**

Run: `python -m pytest -q`
Expected: at least the current 729 tests plus new tests, zero failures.

- [ ] **Step 9: Commit**

Commit message: `feat: wire smart orchestrator into batch runtime`

---

### Task 7: Make conflict resolution and write eligibility visible in the shared audit

**Files:**
- Modify only if needed: `src/product_intelligence/evidence_policy.py`
- Modify only if needed: `src/product_intelligence/final_evidence_gate.py`
- Test: `tests/test_product_evidence_orchestrator.py`
- Test: `tests/test_final_evidence_write_barrier.py`

**Interfaces:**
- Reuse `resolve_evidence_group()`; do not create a second consensus engine.
- Orchestrator records `CONFLICT_UNRESOLVED` and guarantees conflicted fields stay out of write candidates.

- [ ] **Step 1: RED test for two strong contradictory sources**
- [ ] **Step 2: Wire existing consensus outcome to orchestrator field state**
- [ ] **Step 3: Verify final write barrier continues to reject the field**
- [ ] **Step 4: Run GREEN + full regression**
- [ ] **Step 5: Commit**

Commit message: `feat: surface field conflicts in smart resolution`

---

### Task 8: Connect smart execution observability to the real desktop

**Files:**
- Modify: `src/product_intelligence/live_ui_desktop.py` or the smallest inherited run-page mixin actually owning execution logs.
- Modify only if required: `src/product_intelligence/final_live_ui_desktop.py`
- Test: new `tests/test_smart_orchestrator_desktop_contract.py`

**Interfaces:**
- Orchestrator emits/logs stage payloads: `IDENTITY`, `PLAN`, `SOURCE`, `QUERY`, `FOUND`, `VALIDATING`, `ACCEPTED`, `REJECTED`, `FIELDS_ADDED`, `MISSING`, `NEXT_SOURCE`, `FINAL`.
- Existing PDF Review manual UX remains unchanged.

- [ ] **Step 1: RED desktop contract test**
- [ ] **Step 2: Reuse existing run/audit widgets instead of adding a duplicate mode if the general execution already maps to SMART**
- [ ] **Step 3: Show compact counters for verified/missing/conflicted/sources/queries**
- [ ] **Step 4: Verify final desktop shell smoke**
- [ ] **Step 5: Commit**

Commit message: `feat: show smart evidence decisions in desktop`

---

### Task 9: Deterministic generalization and BEFORE/AFTER benchmark

**Files:**
- Extend: `tests/test_product_document_generalization_matrix.py`
- Create: `tests/test_smart_orchestrator_generalization_matrix.py`
- Create or extend benchmark script under existing QA/benchmark location discovered in workflow.

**Interfaces:**
- Minimum matrix: >=12 products/brands and >=8 categories, including at least one non-electronic product if fixtures can prove it without weakening identity policy.
- Output metrics: required, verified before, verified after, PDF contribution, WEB contribution, sources, false positives, missing, conflicted, queries, pages.

- [ ] **Step 1: Add deterministic category/field-routing fixtures**
- [ ] **Step 2: Add sibling/capacity/color/generation/region/no-PDF/blocked-source cases**
- [ ] **Step 3: Prove deterministic false-positive count = 0**
- [ ] **Step 4: Generate BEFORE/AFTER artifact from stable fixtures**
- [ ] **Step 5: Acceptance gate: verified coverage must increase without increasing known false positives**
- [ ] **Step 6: Commit**

Commit message: `test: certify smart orchestrator generalization`

---

### Task 10: Live QA, Windows build and packaged E2E certification

**Files:**
- Modify workflow only if current packaged route does not already exercise `run_batch` smart path: `.github/workflows/build-windows.yml`
- Reuse existing benchmark workflows and packaged smoke machinery.

**Interfaces:**
- Live QA is diagnostic for source/search drift and is not substituted for deterministic CI.
- Packaged `.exe` must traverse: product -> identity -> plan -> PDF and/or WEB -> evidence -> field completion -> write barrier -> output.

- [ ] **Step 1: Run targeted orchestrator tests**
- [ ] **Step 2: Run full regression**
- [ ] **Step 3: Run >=12 product deterministic matrix**
- [ ] **Step 4: Run live Source Validation benchmark and PDF discovery smoke on the exact final head**
- [ ] **Step 5: Build Windows `ProductIntelligence.exe` from the exact final head**
- [ ] **Step 6: Execute packaged E2E using the same smart path**
- [ ] **Step 7: Capture physical PDF/output evidence where applicable**
- [ ] **Step 8: Produce required final report including known limitations**
- [ ] **Step 9: Keep PR draft/no version bump unless every release gate is genuinely satisfied**

---

## Plan self-review

- Spec coverage: orchestrator, shared evidence state, required/missing fields, per-field routing, PDF/WEB collaboration, conflicts, early stop, write gate, UI, deterministic/generalization/live/Windows/packaged E2E and BEFORE/AFTER all have explicit tasks.
- Placeholder scan: no TBD/TODO implementation placeholders.
- Type consistency: later tasks consume only interfaces defined in Tasks 2–5 or existing repo contracts.
- Scope: source adapters that require unavailable credentials/licenses are not invented; the router initially selects among existing engines and records unavailable tiers. Dedicated provider adapters can be added later behind the same `SourceIntent` interface without changing orchestration semantics.
