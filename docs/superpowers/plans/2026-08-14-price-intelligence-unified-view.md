# Unified Price Intelligence View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Price Intelligence self-contained, visibly report zero-result coverage, show all validated offers, and use the intended 48-source intelligent search budget.

**Architecture:** Keep the existing `price_workflow.py` engine and its identity/quality gates. Change the desktop layer so one Price Intelligence module owns its progress, offers, coverage, and audit presentation. Feed coverage and event rows from the existing event stream into internal tabs; do not duplicate search engines or bypass validation.

**Tech Stack:** Python 3.12, Tkinter/ttk, existing PriceOffer models, pytest, GitHub Actions, PyInstaller Windows bundle.

## Global Constraints

- Base branch: `release/windows`.
- Do not touch `main`.
- Preserve strict marketplace validation, Peru filtering, dedupe and outlier filtering.
- Part Number/MPN remains the preferred search identity.
- Zero offers is a valid completed outcome, not a fatal UI state.
- Publish only after full CI and Windows release gate pass.

---

### Task 1: Price module result model and zero-result coverage

**Files:**
- Modify: `src/product_intelligence/price_desktop.py`
- Test: `tests/test_price_unified_view.py`

**Interfaces:**
- Consumes: existing price event payloads from `run_price_product` (`source`, `page`, `coverage`, `offer`, `done`).
- Produces: `_render_price_coverage(report: dict) -> None`, `_append_price_audit(event: dict) -> None`.

- [ ] **Step 1: Write failing tests** asserting the module contains internal tabs `Ofertas`, `Cobertura`, `Auditoría`, renders all coverage rows including `NO_HAY`, and shows a completed zero-offer message.
- [ ] **Step 2: Run** `python -m pytest -q tests/test_price_unified_view.py` and confirm RED.
- [ ] **Step 3: Implement minimal UI/event rendering** in `price_desktop.py`.
- [ ] **Step 4: Run** `python -m pytest -q tests/test_price_unified_view.py` and confirm GREEN.
- [ ] **Step 5: Commit** UI result changes.

### Task 2: Intelligent breadth and all-valid-offer retention

**Files:**
- Modify: `src/product_intelligence/price_desktop.py`
- Test: `tests/test_price_intelligent_search_contract.py`

**Interfaces:**
- Consumes: `run_price_product(identity, output_root, on_event=..., max_sources=48)`.
- Produces: desktop execution using the workflow's intended 48-source budget while leaving final quality gates in `price_workflow.py` unchanged.

- [ ] **Step 1: Write failing tests** asserting desktop no longer hardcodes `max_sources=12`, uses 48, and does not truncate validated offer rows before insertion.
- [ ] **Step 2: Run** `python -m pytest -q tests/test_price_intelligent_search_contract.py` and confirm RED.
- [ ] **Step 3: Change only the desktop source budget to 48** and keep every emitted validated `offer` event visible.
- [ ] **Step 4: Run** the focused tests and confirm GREEN.
- [ ] **Step 5: Commit** discovery-budget change.

### Task 3: Regression and release v0.10.15

**Files:**
- Modify: `src/product_intelligence/version.py`
- Modify: `pyproject.toml`
- Modify: version contract tests that explicitly pin `0.10.14`.

**Interfaces:**
- Produces: `APP_VERSION == "0.10.15"` and package version `0.10.15`.

- [ ] **Step 1: Run full suite** `python -m pytest -q` and fix only regressions caused by Tasks 1-2.
- [ ] **Step 2: Bump version contracts to `0.10.15`**.
- [ ] **Step 3: Run full suite again** and require zero failures.
- [ ] **Step 4: Merge PR into `release/windows` only after CI is green**.
- [ ] **Step 5: Follow `Release Windows` through regression tests, desktop smoke, PyInstaller, executable verification, updater bootstrap, ZIP/SHA256 and release publication.
