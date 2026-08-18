# ProductIntelligence Recovery Updater Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Windows recovery executable that upgrades a broken-updater v0.10.4 installation to the latest verified GitHub Release.

**Architecture:** Keep recovery isolated in `src/product_intelligence/recovery_updater.py`; reuse the published release contract rather than changing the main updater. Build a onefile PyInstaller executable with its own Windows-only GitHub Actions workflow and require an isolated TEMP self-test before artifact upload.

**Tech Stack:** Python 3.12, requests, zipfile, hashlib, tkinter, ctypes, PyInstaller, GitHub Actions Windows runner.

## Global Constraints

- Do not modify scraping, OCR.space, Mistral, PDF evidence, Multimedia, Price Intelligence, Configuration, API keys, or main application behavior.
- Do not modify `main`.
- Recovery target is the existing portable ProductIntelligence installation.
- Latest release must provide `ProductIntelligence-Windows.zip` and `ProductIntelligence-Windows.sha256`.
- SHA256 verification is mandatory before applying files.
- The recovery EXE must run standalone from an isolated directory.

---

### Task 1: Recovery contracts and core utility

**Files:**
- Create: `tests/test_recovery_updater.py`
- Create: `src/product_intelligence/recovery_updater.py`

**Interfaces:**
- Produces: `discover_target_dir(executable_path: Path, cwd: Path) -> tuple[Path | None, int | None]`
- Produces: `parse_sha256(text: str) -> str`
- Produces: `select_release_assets(payload: dict) -> tuple[str, str, str]`
- Produces: `safe_extract_bundle(zip_path: Path, stage_dir: Path) -> Path`
- Produces: `recover(target_dir: Path, *, session=requests) -> str`

- [ ] Write tests that fail because the module does not exist, covering sibling/cwd target discovery, SHA parsing, release asset selection, path traversal rejection, and expected ProductIntelligence bundle root.
- [ ] Run `python -m pytest tests/test_recovery_updater.py -q` and confirm RED.
- [ ] Implement only the recovery functions required by those tests.
- [ ] Run `python -m pytest tests/test_recovery_updater.py -q` and confirm PASS.
- [ ] Commit core utility and tests.

### Task 2: One-click Windows entry point

**Files:**
- Modify: `src/product_intelligence/recovery_updater.py`
- Create: `run_recovery_updater.py`

**Interfaces:**
- Produces: `main(argv: list[str] | None = None) -> int`
- Supports: `--self-test` returning exit code 0 without network or installation mutation.

- [ ] Add tests for `--self-test` and no-target fail-closed behavior.
- [ ] Run focused tests and confirm RED.
- [ ] Implement tkinter status/error messages, running-process path discovery on Windows, wait-for-exit behavior, verified download, overlay copy, restart, and `--self-test`.
- [ ] Run focused tests and confirm PASS.
- [ ] Commit entry point.

### Task 3: Standalone PyInstaller build contract

**Files:**
- Create: `ProductIntelligenceRecovery.spec`
- Modify: `tests/test_recovery_updater.py`

**Interfaces:**
- Produces: `dist/ProductIntelligenceRecoveryUpdater.exe`

- [ ] Add a test asserting the recovery spec exists, targets `run_recovery_updater.py`, names `ProductIntelligenceRecoveryUpdater`, and uses a standalone onefile EXE contract.
- [ ] Run the focused contract and confirm RED.
- [ ] Add the minimal PyInstaller spec.
- [ ] Run the focused contract and confirm PASS.
- [ ] Commit packaging contract.

### Task 4: Windows Actions build and isolated smoke

**Files:**
- Create: `.github/workflows/build-recovery-updater.yml`
- Modify: `tests/test_recovery_updater.py`

**Interfaces:**
- Produces Actions artifact: `ProductIntelligenceRecoveryUpdater-Windows`
- Artifact contains exactly: `ProductIntelligenceRecoveryUpdater.exe`

- [ ] Add a workflow contract test requiring `windows-latest`, PyInstaller build, isolated `$env:RUNNER_TEMP` smoke, `--self-test`, and artifact upload.
- [ ] Run focused test and confirm RED.
- [ ] Add workflow triggered by push to `fix/recovery-updater-v0104` and manual dispatch.
- [ ] Run full pytest and confirm PASS.
- [ ] Push and verify GitHub Actions build succeeds.
- [ ] Verify the Windows smoke executes the built recovery EXE from an isolated temporary directory.
- [ ] Download the Actions artifact and deliver the executable to the user.
