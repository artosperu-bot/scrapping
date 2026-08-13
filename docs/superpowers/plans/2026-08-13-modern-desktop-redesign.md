# Modern Desktop Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the visibly old notebook-first desktop shell with a genuinely modern sidebar/dashboard experience while preserving the existing scraping, Excel, media, price, output, and audit behavior.

**Architecture:** Add a dedicated final presentation shell on top of the existing `price_desktop.App` workflow surface. The shell will hide the notebook tab strip, add persistent navigation, introduce a dashboard, apply a cohesive ttk theme, and reuse the existing pages/callbacks rather than rewriting business logic. `run_desktop.py` will point to the new final shell.

**Tech Stack:** Python 3.12, Tkinter/ttk, Pillow, existing Product Intelligence workflow modules, pytest, PyInstaller, GitHub Actions.

## Global Constraints

- Do not rewrite the scraping engine, Excel mapping/preflight logic, price intelligence, media workflow, identity validation, or output contracts.
- Opening the executable must be visually and structurally distinguishable from the previous notebook-based build immediately.
- Persistent left navigation replaces numbered notebook tabs as the primary application shell.
- Dashboard is the initial workspace.
- Products, Sources, Attributes, Multimedia, Prices, Execute, and Audit remain usable.
- Long-running work remains off the Tk main thread.
- Existing functional tests remain mandatory.
- Windows build must verify `dist\\ProductIntelligence\\ProductIntelligence.exe` and upload `ProductIntelligence-Windows`.

---

### Task 1: Contract tests for the final modern shell

**Files:**
- Create: `tests/test_modern_desktop.py`
- Consume: `src/product_intelligence/price_desktop.py`
- Future create: `src/product_intelligence/modern_desktop.py`

**Interfaces:**
- Consumes: existing `price_desktop.App` callbacks and `self.notebook` pages.
- Produces: assertions for `NAV_ITEMS`, modern shell inheritance, dashboard-first selection, hidden notebook tabs, and final entrypoint.

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

from product_intelligence import modern_desktop
from product_intelligence.price_desktop import App as PriceApp


def test_modern_shell_wraps_final_price_app():
    assert issubclass(modern_desktop.App, PriceApp)


def test_modern_shell_has_primary_destinations():
    assert [item[0] for item in modern_desktop.NAV_ITEMS] == [
        "Inicio", "Productos", "Fuentes", "Atributos",
        "Multimedia", "Precios", "Ejecutar", "Auditoría",
    ]


def test_desktop_entrypoint_uses_modern_shell():
    text = Path("run_desktop.py").read_text(encoding="utf-8")
    assert "product_intelligence.modern_desktop import main" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_modern_desktop.py -q`
Expected: FAIL because `modern_desktop` does not yet exist and entrypoint still targets `price_desktop`.

- [ ] **Step 3: Commit the failing contract test**

```bash
git add tests/test_modern_desktop.py
git commit -m "test: define modern desktop shell contract"
```

### Task 2: Modern shell, navigation, theme, and dashboard

**Files:**
- Create: `src/product_intelligence/modern_desktop.py`
- Modify: `run_desktop.py`
- Test: `tests/test_modern_desktop.py`

**Interfaces:**
- Consumes: `price_desktop.App`, `self.notebook`, `self.excel`, `self.out`, `self.product_rows`, `analyze_excel`, `pick_excel`, `pick_out`.
- Produces: `NAV_ITEMS`, `App`, `main`, `_show_workspace(key)`, `_refresh_dashboard()`, and modern ttk styles.

- [ ] **Step 1: Implement a dedicated shell class**

Create `modern_desktop.py` with these explicit responsibilities:

```python
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .price_desktop import App as PriceApp

NAV_ITEMS = [
    ("Inicio", "dashboard"),
    ("Productos", "products"),
    ("Fuentes", "sources"),
    ("Atributos", "attributes"),
    ("Multimedia", "media"),
    ("Precios", "prices"),
    ("Ejecutar", "run"),
    ("Auditoría", "audit"),
]


class App(PriceApp):
    def __init__(self):
        self._nav_buttons = {}
        self._workspace_tabs = {}
        self._dashboard_vars = {}
        super().__init__()
        self.title("Product Intelligence — STECH")
        self.geometry("1480x920")
        self.minsize(1180, 760)
        self._apply_modern_theme()
        self._install_modern_shell()
        self._show_workspace("dashboard")

    def _apply_modern_theme(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("App.TFrame", background="#f4f6f9")
        style.configure("Sidebar.TFrame", background="#172033")
        style.configure("SidebarTitle.TLabel", background="#172033", foreground="#ffffff", font=("Segoe UI", 15, "bold"))
        style.configure("SidebarMuted.TLabel", background="#172033", foreground="#a9b4c8", font=("Segoe UI", 9))
        style.configure("Nav.TButton", anchor="w", padding=(18, 11), font=("Segoe UI", 10))
        style.configure("NavActive.TButton", anchor="w", padding=(18, 11), font=("Segoe UI", 10, "bold"))
        style.configure("PageTitle.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("PageSubtitle.TLabel", foreground="#5f6b7a", font=("Segoe UI", 10))
        style.configure("Card.TLabelframe", padding=12)
        style.configure("Primary.TButton", padding=(16, 10), font=("Segoe UI", 10, "bold"))

    def _install_modern_shell(self):
        # Reuse the existing notebook pages, but hide their numbered tab strip and
        # drive page selection from a persistent sidebar. A dashboard page is
        # inserted at index 0 and is the initial view.
        ...
```

The implementation must complete the omitted shell code with these exact behaviors:
- identify the existing `self.notebook` and its parent frame;
- hide notebook tab chrome with a dedicated `Modern.TNotebook` style (`tabmargins=0`, tabs layout empty);
- create a persistent left sidebar in the same root-level content frame;
- create a header/status strip above the notebook content;
- insert a new dashboard page at notebook index `0`;
- map existing page widgets to Products, Sources, Attributes, Execute, Audit, Multimedia, and Prices by page text, not fragile numeric indices;
- create navigation buttons that call `_show_workspace(key)`;
- keep all pre-existing page widgets/callbacks alive;
- dashboard cards show workbook path/state, product count, output folder, and workflow readiness;
- dashboard includes `Seleccionar Excel`, `Analizar`, and `Abrir ejecución` actions.

- [ ] **Step 2: Point the packaged entrypoint to the modern shell**

Replace `run_desktop.py` with:

```python
from product_intelligence.modern_desktop import main

# Final desktop entry point: modern shell over the preserved Product Intelligence engine.
main()
```

- [ ] **Step 3: Make dashboard state refresh after workbook analysis**

Override `analyze_excel()` only to call the parent implementation and then `_refresh_dashboard()`; do not duplicate workbook parsing.

- [ ] **Step 4: Run the modern-shell contract tests**

Run: `python -m pytest tests/test_modern_desktop.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/modern_desktop.py run_desktop.py tests/test_modern_desktop.py
git commit -m "feat: add modern sidebar desktop shell"
```

### Task 3: Preserve page behavior and improve presentation hierarchy

**Files:**
- Modify: `src/product_intelligence/modern_desktop.py`
- Test: `tests/test_modern_desktop.py`

**Interfaces:**
- Consumes: existing page widgets such as `products_tree`, `sources_tree`, `attrs_tree`, `media_*`, `price_*`, `run_summary`, `log`.
- Produces: `_restyle_existing_pages()` and `_sync_global_status()`.

- [ ] **Step 1: Extend tests for preserved destinations and callbacks**

Add static/contract assertions that `modern_desktop.App` does not override `_start_price_indices`, `_start_media_indices`, `run`, or `repair_jsons`; these must stay inherited from the working engine.

- [ ] **Step 2: Implement presentation-only restyling**

`_restyle_existing_pages()` must:
- standardize Treeview row height and headings;
- style primary action buttons without changing their commands;
- remove visible numeric prefixes from user-facing section headings where possible;
- keep the wolf/progress widget but place emphasis on progress/status rather than decoration;
- set readable padding around existing workspaces;
- leave all data bindings untouched.

- [ ] **Step 3: Add a global status strip**

Create one `StringVar` in the shell. Mirror high-level status from existing `analysis_status`, media status, and price status using Tk variable traces where available. Errors remain present in Audit; the strip is supplementary.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_modern_desktop.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/modern_desktop.py tests/test_modern_desktop.py
git commit -m "feat: polish modern desktop workspaces"
```

### Task 4: Full regression and Windows build gate

**Files:**
- Verify: `.github/workflows/build-windows.yml`
- Verify: `ProductIntelligence.spec`
- No business-logic changes unless a regression proves the shell integration broke a contract.

**Interfaces:**
- Produces: a passing repository regression and a fresh Windows artifact tied to the redesign commit.

- [ ] **Step 1: Run the complete regression suite**

Run: `python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 2: Verify entrypoint and PyInstaller spec compatibility**

Confirm the spec still packages `run_desktop.py`, Pillow assets, Playwright/Chromium bundle, and package modules required by the modern shell.

- [ ] **Step 3: Push/commit any test-only compatibility fix if required**

Any compatibility fix must remain presentation/build scoped and must not weaken product identity, price validation, media validation, Excel mapping, or output rules.

- [ ] **Step 4: Let `Build Windows EXE` run on the final `main` commit**

Required successful steps:
- Install desktop profile
- Run regression tests
- Install bundled Chromium
- Build clean desktop bundle
- Verify executable exists
- Upload artifact

- [ ] **Step 5: Verify the fresh artifact**

Confirm:
- workflow conclusion: `success`;
- `dist\\ProductIntelligence\\ProductIntelligence.exe` verification step: `success`;
- artifact name: `ProductIntelligence-Windows`;
- artifact head SHA equals the final redesign commit;
- artifact is not expired.

- [ ] **Step 6: Final completion statement**

Only claim completion after all gates above are evidenced. Report the final commit SHA, workflow run number/ID, artifact ID, and whether all tests passed.
