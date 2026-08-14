# Organized Progress Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize ProductIntelligence desktop progress views so the shared GIF is clearly visible and Price Intelligence, Multimedia, and Scraping Excel read more cleanly, without changing functional workflows or process logic.

**Architecture:** Preserve all current workflow invocations, callbacks, queue/event handling, widget names consumed by event handlers, and progress semantics. Change only Tkinter container/layout construction in the desktop view modules and add contract tests that pin visual dimensions/structure plus functional invariants.

**Tech Stack:** Python 3.12, Tkinter/ttk, Pillow GIF rendering, pytest, GitHub Actions Windows build.

## Global Constraints

- Visual-only changes.
- Do not modify `price_workflow.py`, `media_workflow.py`, scraping/canonical/resolution logic, OCR/Mistral provider logic, updater logic, or release logic.
- Reuse `ProgressAnimation`, `processing.gif`, and `completed.gif`.
- No fake percentages or new process states.
- Preserve callbacks, queue/event flow, threading, tree bindings, and result columns.
- Keep result areas as the largest expanding regions.
- Never touch `main`; target is `release/windows` only after verification.

---

### Task 1: UI contract tests

**Files:**
- Modify: `tests/test_progress_animation_contract.py`

**Interfaces:**
- Consumes: source text of `price_desktop.py`, `media_progress_desktop.py`, and `pdf_desktop.py`.
- Produces: regression contracts for a visible 220x140-class animation area and preserved workflow invocations.

- [ ] **Step 1: Write failing tests**

Add assertions that Price Intelligence creates `ProgressAnimation(... width=220, height=140)` (or larger), uses a fixed-height progress card with `pack_propagate(False)`, preserves `run_price_product(identity, output_root, on_event=on_event, max_sources=12)`, and keeps the offers Treeview expanding. Add equivalent visibility assertions for Multimedia and Scraping Excel while retaining their existing workflow/event markers.

- [ ] **Step 2: Run the focused contract suite and verify RED**

Run: `python -m pytest tests/test_progress_animation_contract.py -q`
Expected: FAIL only on new layout assertions.

- [ ] **Step 3: Commit RED tests**

Commit message: `test: define organized progress layout contracts`

### Task 2: Price Intelligence visual reorganization

**Files:**
- Modify: `src/product_intelligence/price_desktop.py`
- Test: `tests/test_progress_animation_contract.py`

**Interfaces:**
- Consumes: existing `ProgressAnimation`, all existing callbacks/event methods.
- Produces: same widget attributes and callbacks with a reorganized layout.

- [ ] **Step 1: Rebuild only `_build_price_tab` layout**

Keep header text, `price_product_list`, `price_selected_btn`, `price_all_btn`, `price_status`, progress bars/percent StringVars, `price_summary`, `price_tree`, and bindings unchanged by name. Make the top product/actions row visually balanced. Create a fixed-height dedicated progress card; place textual status and bars on the left and a larger `ProgressAnimation(width=220, height=140)` on the right. Keep summary compact and offers table as the primary expanding area.

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest tests/test_progress_animation_contract.py -q`
Expected: Price layout assertions PASS while remaining pending assertions identify the next views.

- [ ] **Step 3: Commit**

Commit message: `feat: organize price intelligence progress layout`

### Task 3: Multimedia and Scraping Excel progress alignment

**Files:**
- Modify: `src/product_intelligence/media_progress_desktop.py`
- Modify: `src/product_intelligence/pdf_desktop.py`
- Test: `tests/test_progress_animation_contract.py`

**Interfaces:**
- Consumes: existing media events and Excel progress log/state.
- Produces: readable fixed progress cards using existing widgets and semantics.

- [ ] **Step 1: Reorganize Multimedia progress card**

Keep gallery behavior and all progress widget names/events. Reserve enough fixed height and use a larger visible GIF area on the right; keep status/bars/detail on the left.

- [ ] **Step 2: Reorganize Scraping Excel progress area**

Do not alter analysis/OCR/Mistral/PDF/Excel callbacks. Only reserve a clean status/bars/GIF layout and preserve the truthful product counter semantics already driven from logs/events.

- [ ] **Step 3: Run contract suite**

Run: `python -m pytest tests/test_progress_animation_contract.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

Commit message: `feat: align desktop progress views`

### Task 4: Full regression and Windows gate

**Files:**
- No functional source changes expected.

**Interfaces:**
- Consumes: completed visual branch.
- Produces: verified UI-only candidate for `release/windows`.

- [ ] **Step 1: Run full regression suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 2: Run optional capability registry check**

Use the repository's existing CI command/workflow step.
Expected: PASS.

- [ ] **Step 3: Inspect diff scope**

Verify no workflow-engine, scraping, canonical, OCR/Mistral, updater, or release files changed.

- [ ] **Step 4: Open PR to `release/windows` and require CI GREEN**

PR must contain only UI layout/tests/docs. Do not merge until CI is GREEN.
