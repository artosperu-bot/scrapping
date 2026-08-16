# v0.10.20 Provider Certification Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish ProductIntelligence v0.10.20 containing learned price sources plus the already-designed safe OCR.space/Mistral pipeline, with end-to-end certification and immutable release versioning.

**Architecture:** Preserve the existing provider architecture: PyMuPDF native text first, OCR.space only as PDF fallback, and Mistral only for grounded description narration after validated canonical facts. Add an end-to-end resolver contract test and harden the release workflow so an existing version/tag can never have assets overwritten by a different commit. Bump both application and package versions to 0.10.20.

**Tech Stack:** Python 3.12, pytest, GitHub Actions, PowerShell, PyInstaller.

## Global Constraints
- WEB and PDF remain independently selectable.
- OCR.space requires PDF and never bypasses PDF identity/evidence gates.
- Mistral performs narration only; never product-fact extraction.
- Mistral failure/rejection must fall back to deterministic description and must not fail the product.
- Mistral must never introduce unsupported numbers, price, stock, seller, material, certification or compatibility claims.
- Learned price sources from PR #47 remain enabled.
- Existing release assets must never be silently replaced for a tag pointing to another commit.
- Publish as v0.10.20 only after full CI and Windows release gates pass.

---

### Task 1: Certify the Excel description resolver provider seam

**Files:**
- Modify: `tests/test_provider_ocr_mistral_integration.py`

**Interfaces:**
- Consumes: `provider_run_scope`, `resolve_marketplace_field`, existing `DescriptionNarrator` guard.
- Produces: regression proof that Mistral is invoked only for the description field when enabled and returns deterministic fallback on failure/rejection.

- [ ] Add a test resolving a real `description` field under `provider_run_scope(mistral_enabled=True)` with a fake narrator client.
- [ ] Assert grounded narration is returned as `FOUND_DERIVED` and provider audit emits `MISTRAL_DESCRIPTION_REQUESTED`/`ACCEPTED`.
- [ ] Assert an invented-number narration is rejected and deterministic description remains the result.
- [ ] Run focused provider tests.

### Task 2: Make release versions immutable

**Files:**
- Create: `tests/test_release_workflow_version_immutability.py`
- Modify: `.github/workflows/release-windows.yml`

**Interfaces:**
- Produces: release workflow that creates a new release for a new version, permits asset upload only when an existing tag resolves to the current commit, and fails when the same version belongs to another commit.

- [ ] Write a failing source-contract test proving the workflow must not use unconditional `--clobber` for an existing tag.
- [ ] Verify RED against the current workflow.
- [ ] Replace the existing-release branch with tag-target verification; throw `VERSION_ALREADY_RELEASED_FOR_DIFFERENT_COMMIT` on mismatch.
- [ ] Run the focused test and verify GREEN.

### Task 3: Version v0.10.20

**Files:**
- Modify: `src/product_intelligence/version.py`
- Modify: `pyproject.toml`
- Update stale version assertions if tests require it.

**Interfaces:**
- Produces: application/package version `0.10.20` consistently.

- [ ] Change both version sources to `0.10.20`.
- [ ] Run version-related tests and resolve only stale expected-version assertions.

### Task 4: Full verification and publication

**Files:** no additional production changes unless a gate exposes a root cause.

- [ ] Run full CI on the feature branch.
- [ ] Confirm provider/OCR/Mistral tests pass with no real credentials required.
- [ ] Confirm Price Intelligence regression remains green.
- [ ] Review diff for product/store hardcoding or secret leakage.
- [ ] Merge to `release/windows` only when green.
- [ ] Verify Release Windows completes successfully for the merge commit.
- [ ] Verify GitHub release `v0.10.20` exists, points to the new commit/tag, and contains `ProductIntelligence-Windows.zip` plus `.sha256`.
