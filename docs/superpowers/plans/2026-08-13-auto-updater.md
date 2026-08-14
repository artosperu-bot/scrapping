# ProductIntelligence Auto-Updater Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Windows bundle self-updatable from GitHub Releases with one-click update, preserving user settings and API keys.

**Architecture:** ProductIntelligence checks the latest stable GitHub Release, compares semantic versions, downloads a ZIP plus SHA256 sidecar, verifies integrity, copies a bundled updater executable to `%TEMP%`, launches it, and exits. The updater waits for the parent process, replaces only the installation directory contents, restarts ProductIntelligence, and leaves user configuration/keyring untouched because those live outside the install directory. A release workflow builds the same Windows bundle and publishes the ZIP + checksum as the stable update channel.

**Tech Stack:** Python 3.12, Tkinter, requests, PyInstaller, GitHub Actions/Releases.

## Global Constraints

- Do not modify `main` directly.
- Preserve existing PDF, OCR.space, Mistral, Multimedia, and Price Intelligence behavior.
- Do not store credentials in the installation directory or release package.
- Update only after SHA256 verification succeeds.
- A failed update check/download must be non-fatal and must not damage the current installation.
- Windows updater must run from a temporary copy so it can replace `ProductIntelligenceUpdater.exe` in the installation directory.

---

### Task 1: Version and release client

**Files:**
- Create: `src/product_intelligence/version.py`
- Create: `src/product_intelligence/update_service.py`
- Test: `tests/test_auto_updater.py`

**Interfaces:**
- `APP_VERSION: str`
- `ReleaseInfo(version, zip_url, sha256_url, notes, page_url)`
- `UpdateService.check_latest() -> ReleaseInfo | None`
- `UpdateService.download_verified(release, destination_dir) -> Path`

- [ ] Add failing tests for semantic comparison, release parsing, no-update behavior, download and SHA256 verification.
- [ ] Implement the smallest release client using the public GitHub API and injected HTTP session.
- [ ] Keep network exceptions non-fatal at the UI boundary.

### Task 2: External updater process

**Files:**
- Create: `src/product_intelligence/updater.py`
- Create: `run_updater.py`
- Test: `tests/test_auto_updater.py`

**Interfaces:**
- `apply_update(zip_path, target_dir, restart_exe, parent_pid, ...)`
- ZIP must contain a top-level `ProductIntelligence/` directory.

- [ ] Add failing tests for safe extraction, parent wait abstraction, replacement, and rejection of path traversal.
- [ ] Implement staged extraction to a temporary directory and atomic-per-file replacement with retries.
- [ ] Restart the main executable only after all replacement operations complete.

### Task 3: Desktop update UI and launch handoff

**Files:**
- Modify: `src/product_intelligence/provider_desktop.py`
- Test: `tests/test_auto_updater.py`

**Interfaces:**
- Add an `Actualizaciones` card to Configuración.
- `Buscar actualizaciones` performs a background check.
- `Actualizar ahora` downloads/verifies, copies updater to `%TEMP%`, launches it with the current PID, then closes the app.

- [ ] Add tests for expected UI text and updater handoff helpers.
- [ ] Implement manual check plus silent non-blocking startup check.
- [ ] Never auto-install without the user's click.

### Task 4: Package both executables

**Files:**
- Modify: `ProductIntelligence.spec`
- Modify: `.github/workflows/build-windows.yml`
- Test: existing build regression plus `tests/test_auto_updater.py`

- [ ] Add `ProductIntelligenceUpdater.exe` to the PyInstaller COLLECT output.
- [ ] Verify both executables exist before artifact upload.
- [ ] Preserve existing modern/provider desktop smoke tests.

### Task 5: Stable release channel

**Files:**
- Create: `.github/workflows/release-windows.yml`

- [ ] Build on pushes to `release/windows` and optional manual dispatch.
- [ ] Read version from `src/product_intelligence/version.py` and require it to match `pyproject.toml`.
- [ ] Produce `ProductIntelligence-Windows.zip` and `ProductIntelligence-Windows.sha256`.
- [ ] Create/update tag `v<version>` and publish GitHub Release with both assets.
- [ ] Use `contents: write` only in the release workflow.

### Task 6: Verification and first auto-updatable build

- [ ] Run full Windows regression suite.
- [ ] Smoke provider desktop shell.
- [ ] Build clean bundle and verify both EXEs.
- [ ] Publish first stable release from `release/windows`.
- [ ] Download the generated artifact for the user.
