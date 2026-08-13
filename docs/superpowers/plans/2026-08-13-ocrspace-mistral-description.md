# OCR.space + Mistral Description Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent provider configuration, OCR.space fallback OCR, and Mistral `mistral-small-latest` description narration without changing the validated PDF/identity/Excel/media/price contracts.

**Architecture:** Keep PyMuPDF-first extraction and current ProductRecord/evidence pipeline. Add focused provider clients and secure credential abstraction; OCR.space plugs behind the OCR adapter, while Mistral plugs only into the existing description derivation seam with deterministic fallback and an anti-invention guard.

**Tech Stack:** Python 3.10+, Tkinter/ttk, requests, PyMuPDF, Windows Credential Manager/keyring (fallback DPAPI abstraction if packaging requires), pytest, PyInstaller.

## Global Constraints
- Do not replace PyMuPDF-first extraction.
- Mistral performs narration only; never OCR or product fact extraction.
- `mistral-small-latest` is the initial fixed/default model.
- Existing deterministic description remains fallback.
- Never log or serialize plaintext API keys.
- Multimedia and Price Intelligence behavior remains unchanged.
- Remote calls must not block the Tkinter UI thread.
- Existing full regression and Windows release gates must pass before merge/release.

---

### Task 1: Secure provider configuration
**Files:** create `provider_status.py`, `credential_store.py`, `provider_settings.py`; tests `test_provider_configuration.py`.
**Produces:** generic secret CRUD, non-secret settings persistence, shared provider status taxonomy.
- [ ] Write tests for persistence, masking contract, missing credentials, replacement/deletion, and no plaintext secret in settings JSON.
- [ ] Run focused tests and confirm RED.
- [ ] Implement minimal modules.
- [ ] Run focused tests and confirm GREEN.
- [ ] Commit.

### Task 2: Provider clients and real connection tests
**Files:** create `ocr_space_client.py`, `mistral_client.py`; tests `test_provider_clients.py`.
**Produces:** `test_connection()` and classified failures; OCR extraction and Mistral chat wrappers.
- [ ] Write mocked HTTP tests for success, auth rejection, timeout, network, rate/quota, provider error, invalid payload.
- [ ] Confirm RED.
- [ ] Implement with `requests`; OCR.space POST `/parse/image` with `apikey` header, Mistral POST `/v1/chat/completions` with Bearer auth.
- [ ] Confirm GREEN and that secrets never appear in errors/results.
- [ ] Commit.

### Task 3: OCR.space behind existing OCR seam
**Files:** modify `ocr_adapter.py`, `pdf_extract.py`; tests `test_ocrspace_pdf_fallback.py`.
**Produces:** PyMuPDF native text first; remote OCR only when native text is insufficient; PaddleOCR remains optional fallback.
- [ ] Test text PDF never calls OCR.space.
- [ ] Test empty/scanned page calls OCR.space only when configured/enabled.
- [ ] Test provider failure is non-fatal and local fallback behavior remains compatible.
- [ ] Implement provider selection without changing pipeline identity validation.
- [ ] Run PDF/OCR regression and commit.

### Task 4: Grounded Mistral description narrator
**Files:** create `description_narrator.py`; minimally modify description derivation seam; tests `test_mistral_description_narrator.py`.
**Produces:** validated-facts prompt builder, `mistral-small-latest` narrator, anti-invention guard, deterministic fallback.
- [ ] Test prompt excludes price/stock/seller/rejected/conflicting raw content.
- [ ] Test valid commercial Spanish narration accepted.
- [ ] Test new number/unit, altered identity, price/stock or unsupported claims rejected.
- [ ] Test disabled/down Mistral returns existing deterministic description.
- [ ] Implement and run description/marketplace regression.
- [ ] Commit.

### Task 5: One Configuración workspace
**Files:** extend final desktop shell (prefer a focused inherited shell rather than rewriting existing pages); adjust `run_desktop.py`/PyInstaller hidden imports if required; tests `test_provider_settings_desktop.py`.
**Produces:** one Configuración page with OCR.space and Mistral masked keys, model display, status, save/replace/delete behavior, real connection buttons in worker threads.
- [ ] Test navigation and default states without network.
- [ ] Test keys are never rendered in plaintext after persistence.
- [ ] Test connection callbacks classify provider result.
- [ ] Implement single workspace; preserve existing Scraping Excel/Multimedia/Precios/Auditoría pages.
- [ ] Run desktop regression and commit.

### Task 6: Run-context integration and audit
**Files:** extend existing execution/provider context minimally; tests `test_provider_run_isolation.py`.
**Produces:** per-run non-secret flags/model snapshot; credential lookup only inside worker; provider audit events without secrets.
- [ ] Test changing UI settings during a run does not change that run.
- [ ] Test audit contains provider/status but no key/header.
- [ ] Implement minimal context wiring.
- [ ] Run isolation/audit regression and commit.

### Task 7: Full verification and Windows EXE
**Files:** `ProductIntelligence.spec` only if hidden imports/dependency collection require it; no unrelated refactor.
- [ ] Run full pytest on branch through CI.
- [ ] Review diff for accidental product-specific logic and secret leakage.
- [ ] Merge only after all branch checks are green.
- [ ] Let `main` trigger Build Windows EXE.
- [ ] Require Windows regression, desktop smoke, Chromium, PyInstaller, executable existence, artifact upload = PASS.
- [ ] Download and inspect artifact; confirm `ProductIntelligence.exe` exists.
