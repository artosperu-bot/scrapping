# Workspace and UI Organization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Organize Trabajos, Multimedia, and Precios while preserving all existing engines and making workspace files safe across updates.

**Architecture:** Add a focused workspace-path service for physical folders, extend workspace repository with delete-only metadata support, and keep destructive filesystem operations in the desktop/application layer. Recompose existing Tkinter controls into nested notebooks without changing media/price engine entry points.

**Tech Stack:** Python 3, pathlib/shutil, sqlite3, Tkinter/ttk, pytest.

## Global Constraints

- Base branch is `release/windows`; never touch `main`.
- Do not change scraping, PDF, media discovery/download, price workflow, OCR/Mistral, updater, or identity semantics.
- Keep `workspaces.db` in the existing persistent app-data location.
- Default physical root on Windows is `Documents/ProductIntelligence/Trabajos`.
- Normal `Eliminar trabajo` preserves files.
- Physical delete is a separate confirmed action.

---

### Task 1: Workspace physical paths

**Files:**
- Create: `src/product_intelligence/workspace_paths.py`
- Create: `tests/test_workspace_paths.py`

**Interfaces:**
- `default_jobs_root() -> Path`
- `workspace_dir(root: Path, workspace_id: str, name: str) -> Path`
- `ensure_workspace_layout(root: Path, workspace_id: str, name: str) -> dict[str, Path]`
- `clean_workspace_results(path: Path) -> None`
- `delete_workspace_files(path: Path) -> None`

- [ ] Write tests for Windows-invalid characters, duplicate names using distinct IDs, folder creation, clean preserving `Excel`, and full physical delete.
- [ ] Run focused tests and verify RED.
- [ ] Implement path helpers with `Path.home()/Documents/ProductIntelligence/Trabajos` fallback and safe filesystem operations.
- [ ] Run focused tests and verify GREEN.

### Task 2: Workspace repository deletion

**Files:**
- Modify: `src/product_intelligence/workspaces.py`
- Modify: `tests/test_workspaces.py`

**Interfaces:**
- `WorkspaceRepository.delete_workspace(workspace_id: str) -> None`

- [ ] Add tests proving cascade deletion of products/runs/stages while unrelated workspaces survive.
- [ ] Run focused test RED.
- [ ] Implement a single transactional delete after verifying workspace existence.
- [ ] Run focused test GREEN.

### Task 3: Trabajos controls and safe output activation

**Files:**
- Modify: `src/product_intelligence/workspace_desktop.py`
- Create: `tests/test_workspace_desktop_management.py`

- [ ] Add source-level/UI contract tests for `Abrir carpeta`, `Eliminar trabajo`, `Eliminar trabajo y archivos...`, `Limpiar resultados` and active-run guards.
- [ ] Run focused test RED.
- [ ] On create/open, call `ensure_workspace_layout()` and set `self.out` to the workspace root so inherited engines keep their existing subfolder conventions.
- [ ] Implement delete-record-only, confirmed delete-with-files, clean-results, open-folder, and running guards.
- [ ] Run focused test GREEN.

### Task 4: Multimedia nested layout

**Files:**
- Modify: `src/product_intelligence/media_desktop.py`
- Modify: `src/product_intelligence/media_progress_desktop.py`
- Modify: `tests/test_desktop_media_tab.py`
- Modify: `tests/test_media_progress_ui.py`

- [ ] Add tests requiring nested tabs `Buscar`, `Galería`, `Auditoría` and local audit tree.
- [ ] Run focused tests RED.
- [ ] Reparent/rebuild controls into nested tabs while retaining `_start_media_indices()` and `run_media_product()` calls unchanged.
- [ ] Mirror existing media events into an audit tree; do not alter event meaning.
- [ ] Run focused tests GREEN.

### Task 5: Price nested layout

**Files:**
- Modify: `src/product_intelligence/price_desktop.py`
- Modify: `tests/test_price_desktop.py`
- Modify: `tests/test_price_unified_view.py`

- [ ] Add tests requiring nested `Buscar`, `Ofertas`, `Cobertura`, `Auditoría` tabs.
- [ ] Run focused tests RED.
- [ ] Move product/actions/progress to `Buscar`; keep existing offer/coverage/audit tree objects and callbacks.
- [ ] Run focused tests GREEN.

### Task 6: Regression and Windows release readiness

**Files:**
- Modify only if tests reveal a real integration issue.

- [ ] Run `pytest -q` and require full GREEN.
- [ ] Run existing media and price integration smoke workflows.
- [ ] Verify source-validation work remains isolated on its separate branch.
- [ ] Open PR to `release/windows` with no `main` changes.
