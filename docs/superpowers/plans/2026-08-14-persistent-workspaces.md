# Persistent Workspaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent multi-job workspaces, safe resume semantics and template profiles without replacing existing ProductIntelligence engines.

**Architecture:** Introduce focused domain, SQLite repository, orchestration and template-profile modules. Integrate only a new `Trabajos` page into the modern shell; existing scraping/media/price/PDF/canonical workflows remain inherited and unchanged.

**Tech Stack:** Python 3.10+, stdlib `sqlite3`, `dataclasses`, `enum`, `uuid`, Tkinter, pytest.

## Global Constraints
- Base from `release/windows` v0.10.9.
- Do not modify `main`.
- Preserve all v0.10.4+ validated engines and updater behavior.
- No new third-party dependency.
- Evidence before claims; full regression before merge.

---

### Task 1: Domain and SQLite persistence
**Files:**
- Create: `src/product_intelligence/workspaces.py`
- Test: `tests/test_workspaces.py`

**Interfaces:**
- Produces `Stage`, `RunStatus`, `WorkspaceRepository`, `Workspace`, `WorkspaceProduct`, `ProductRun`, `StageState`.

- [ ] Write tests for create/reopen persistence and isolation.
- [ ] Verify RED through PR CI.
- [ ] Implement schema, models and repository methods.
- [ ] Verify GREEN.

### Task 2: Resume orchestration
**Files:**
- Create: `src/product_intelligence/workspace_service.py`
- Test: `tests/test_workspace_service.py`

**Interfaces:**
- Consumes `WorkspaceRepository`, `Stage`, `RunStatus`.
- Produces `WorkspaceService.recover_interrupted_runs()` and `next_stage(run_id)`.

- [ ] Write tests proving RUNNING -> PENDING recovery and COMPLETED skip semantics.
- [ ] Verify RED.
- [ ] Implement minimal orchestration.
- [ ] Verify GREEN.

### Task 3: Template profiles
**Files:**
- Create: `src/product_intelligence/template_profiles.py`
- Test: `tests/test_template_profiles.py`

**Interfaces:**
- Produces `TemplateProfile`, `TemplateProfileRegistry`, `map_canonical()`.

- [ ] Write tests for mapping and canonical immutability.
- [ ] Verify RED.
- [ ] Implement profile registry and mapping.
- [ ] Verify GREEN.

### Task 4: Modern desktop Trabajos page
**Files:**
- Modify: `src/product_intelligence/modern_desktop.py`
- Test: `tests/test_modern_desktop_workspaces.py`

**Interfaces:**
- Adds navigation key `workspaces` and persistent workspace page while preserving inherited callbacks.

- [ ] Write structural navigation tests.
- [ ] Verify RED.
- [ ] Add page and basic create/select/reopen actions.
- [ ] Verify GREEN.

### Task 5: Regression and review
- [ ] Run full `pytest -q` in GitHub Actions.
- [ ] Inspect PR diff for unrelated changes.
- [ ] Confirm `release/windows` and `main` unchanged.
- [ ] Do not merge until gates are green.
