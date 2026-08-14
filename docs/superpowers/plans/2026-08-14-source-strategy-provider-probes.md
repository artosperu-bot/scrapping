# Source Strategy + Provider Probes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-run Web/PDF/OCR/Mistral routing controls and real OCR.space/Mistral connection probes, then publish Windows v0.10.14.

**Architecture:** Keep one existing scraping/evidence pipeline. Add a small source-strategy boundary passed from `pdf_desktop.py` into `batch.py`; provider flags remain in `provider_run_scope`. Add provider-probe helpers that reuse the existing clients and secure key store, and invoke them asynchronously from `provider_desktop.py`.

**Tech Stack:** Python 3.12, Tkinter/ttk, requests, PyMuPDF, Pillow, existing OCRSpaceClient/MistralClient, pytest, GitHub Actions, PyInstaller.

## Global Constraints

- Base is `release/windows`; `main` remains untouched.
- Target version is `0.10.14`.
- Source selections are per execution and are not persisted as defaults.
- At least one of Web or PDF must be enabled.
- OCR requires PDF and is forced off when PDF is off.
- Identity/evidence/canonical/conflict/Excel safeguards remain unchanged.
- API keys never enter snapshots, logs, audit output, Excel, or business JSON.

---

### Task 1: Source strategy domain and routing contract

**Files:**
- Create: `src/product_intelligence/source_strategy.py`
- Modify: `src/product_intelligence/batch.py`
- Test: `tests/test_source_strategy_routing.py`

**Interfaces:**
- Produces: `SourceStrategy(web: bool = True, pdf: bool = True, ocr: bool = True, mistral: bool = True)` with `normalized()` and `as_options()`.
- `run_batch(..., source_strategy: SourceStrategy | None = None)` passes the strategy to `scrape_item(..., source_strategy=...)`.

- [ ] **Step 1: Write failing strategy/routing tests**

Tests must assert default all-on behavior, OCR forced off when PDF is off, rejection when both Web/PDF are off, and source code boundaries in `batch.py`: Web-off does not call normal `search_web`/`search_web_for_fields`; PDF-off does not call `discover_product_documents`.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python -m pytest -q tests/test_source_strategy_routing.py`
Expected: FAIL because `SourceStrategy` and routing parameters do not exist.

- [ ] **Step 3: Implement minimal source strategy and batch routing**

Create a frozen dataclass. `normalized()` returns a copy where `ocr=False` whenever `pdf=False` and raises `ValueError("SOURCE_STRATEGY_REQUIRES_WEB_OR_PDF")` when both acquisition routes are false.

In `scrape_item`:
- build manual candidates as today, but skip non-PDF manual candidates when `web=False`;
- call `search_web()` only when `web=True`;
- keep direct `discover_product_documents()` only when `pdf=True`;
- call `search_web_for_fields()` only when `web=True`;
- pass `include_pdfs=strategy.pdf` into page processing.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run: `python -m pytest -q tests/test_source_strategy_routing.py`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add per-run source strategy routing`

---

### Task 2: Scraping Excel strategy controls and execution snapshot

**Files:**
- Modify: `src/product_intelligence/pdf_desktop.py`
- Test: `tests/test_source_strategy_desktop.py`

**Interfaces:**
- Consumes: `SourceStrategy` from Task 1.
- Produces Tk variables `source_web_enabled`, `use_pdf_evidence`, `ocr_run_enabled`, `mistral_run_enabled` plus preset methods and execution snapshot options.

- [ ] **Step 1: Write failing desktop contract tests**

Assert the UI contains `Fuentes de esta ejecución`, `Web / HTML`, `PDF`, `OCR.space`, `Mistral`, and preset labels `Automático`, `Solo Web`, `Solo PDF`, `Web + PDF`. Assert `run()` snapshots `source_web_enabled`, `source_pdf_enabled`, `ocr_space_enabled`, `mistral_enabled` and passes a `SourceStrategy` into `run_batch`.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python -m pytest -q tests/test_source_strategy_desktop.py`
Expected: FAIL because controls/options do not exist.

- [ ] **Step 3: Implement controls and dependencies**

Replace the single PDF checkbox block with one strategy block. Initialize per-run variables from safe current provider availability but do not save changes back to `ProviderSettings`.

Preset behavior:
- Automático => Web=True, PDF=True, OCR=stored `ocr_space_enabled`, Mistral=stored `mistral_enabled`.
- Solo Web => Web=True, PDF=False, OCR=False; keep current Mistral checkbox unchanged.
- Solo PDF => Web=False, PDF=True, OCR=stored `ocr_space_enabled`; keep current Mistral checkbox unchanged.
- Web + PDF => Web=True, PDF=True; leave OCR/Mistral current checkbox values unchanged.

Before execution, validate Web/PDF and normalize OCR dependency. Record route set in audit STARTED detail. Wrap PDF evidence scope with the selected PDF flag and provider scope with selected OCR/Mistral flags. Pass `SourceStrategy` to `run_batch`.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run: `python -m pytest -q tests/test_source_strategy_desktop.py`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add execution source controls`

---

### Task 3: Provider probe service

**Files:**
- Create: `src/product_intelligence/provider_probe.py`
- Test: `tests/test_provider_probe.py`

**Interfaces:**
- Produces: `ProbeResult(provider: str, status: str, detail: str)`.
- Produces: `probe_ocr_space(*, timeout: int = 20, client=None) -> ProbeResult`.
- Produces: `probe_mistral(*, model: str = "mistral-small-latest", timeout: int = 20, client=None) -> ProbeResult`.

- [ ] **Step 1: Write failing provider probe tests**

Use fake clients. Cover NO_CREDENTIAL, success, provider rejection/empty response, transport exception, and ensure a sentinel secret string never appears in `ProbeResult.detail`.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python -m pytest -q tests/test_provider_probe.py`
Expected: FAIL because module/functions do not exist.

- [ ] **Step 3: Implement probes**

OCR: load secure key, generate an in-memory PNG with Pillow containing `STECH OCR TEST`, call existing `OCRSpaceClient.extract`, return `CONECTADO` for non-empty text, `RECHAZADO` for empty provider result/HTTP provider rejection, `ERROR DE RED` for request transport errors, `SIN CONFIGURAR` without key.

Mistral: load secure key, call existing `MistralClient.generate` with a minimal payload and configured model, return the same statuses. Never return raw exception text if it could include credentials; return exception class/category only.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run: `python -m pytest -q tests/test_provider_probe.py`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add safe provider connectivity probes`

---

### Task 4: Enable real Probar conexión buttons

**Files:**
- Modify: `src/product_intelligence/provider_desktop.py`
- Test: `tests/test_provider_probe_desktop.py`

**Interfaces:**
- Consumes Task 3 probes.
- Produces `_test_provider_connection(provider, status_var)` and worker/finish methods that run without blocking Tk.

- [ ] **Step 1: Write failing UI tests**

Assert `Probar conexión · pendiente` and `state="disabled"` are gone. Assert button command invokes the test handler. Assert thread is daemonized and result is returned to Tk via `after`. Assert UI maps statuses exactly to `PROBANDO…`, `CONECTADO`, `RECHAZADO`, `ERROR DE RED`, `SIN CONFIGURAR`.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python -m pytest -q tests/test_provider_probe_desktop.py`
Expected: FAIL.

- [ ] **Step 3: Implement asynchronous buttons**

Enable each button. Disable only that test button while probing, set status to `PROBANDO…`, run proper probe on a daemon thread, then restore button and display returned status. Keep save/delete credential behavior unchanged.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run: `python -m pytest -q tests/test_provider_probe_desktop.py`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: enable provider connection tests`

---

### Task 5: Version 0.10.14 and regression gate

**Files:**
- Modify: `src/product_intelligence/version.py`
- Modify: `pyproject.toml`
- Modify version-contract tests that currently assert `0.10.13`.

- [ ] **Step 1: Update version contracts to 0.10.14**

Set `APP_VERSION = "0.10.14"` and `[project].version = "0.10.14"`; update only exact version assertions.

- [ ] **Step 2: Run full regression suite**

Run: `python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 3: Open PR to release/windows and wait for CI**

PR title: `feat: source strategy and provider probes for v0.10.14`.
Expected: CI PASS.

- [ ] **Step 4: Merge only after CI PASS**

Merge into `release/windows`; never `main`.

- [ ] **Step 5: Verify Windows release workflow**

Expected PASS steps: version match, regression tests, desktop smoke, Chromium install, clean PyInstaller build, executable/resource verification, standalone updater bootstrap, ZIP/SHA256, GitHub Release.

- [ ] **Step 6: Verify latest release**

`releases/latest` must report tag `v0.10.14` with `ProductIntelligence-Windows.zip` and `ProductIntelligence-Windows.sha256`.
