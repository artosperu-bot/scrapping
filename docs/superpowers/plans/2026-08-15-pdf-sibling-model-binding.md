# PDF Sibling Model Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject PDFs explicitly bound to a sibling model while preserving PDFs bound to the requested model.

**Architecture:** Extend `validate_pdf_identity()` with one narrow URL-model conflict check before content-based acceptance. The check compares compact model-like URL tokens against the requested model using alphabetic skeleton equality, so sibling codes such as `HL-L2480DW` vs `HL-L2460DW` are rejected without treating unrelated numeric URL tokens as product conflicts.

**Tech Stack:** Python 3.12, pytest, existing Product Intelligence PDF identity gate.

## Global Constraints
- User-provided model remains canonical.
- Do not add automatic model discovery.
- Preserve fail-closed source validation.
- No unrelated refactoring.

---

### Task 1: Add regression coverage

**Files:**
- Modify: `tests/test_pdf_identity_binding.py`

**Interfaces:**
- Consumes: `validate_pdf_identity(identity: ProductIdentity, text: str, url: str) -> PdfIdentityMatch`
- Produces: regression contracts for sibling-model URL rejection and exact-model URL acceptance.

- [ ] **Step 1: Write the failing tests**

```python
def test_pdf_rejects_url_explicitly_bound_to_sibling_model():
    identity = ProductIdentity(brand="Brother", model="HL-L2460DW")
    text = "Brother HL-L2460DW and HL-L2480DW user guide."
    match = validate_pdf_identity(identity, text, "https://download.brother.com/cv_hll2480dw_use_psg_e.pdf")
    assert match.accepted is False
    assert match.reason == "sibling_model_url_conflict"


def test_pdf_keeps_exact_requested_model_url_binding():
    identity = ProductIdentity(brand="Dell", model="P2422H")
    text = "Dell P2422H Monitor User's Guide."
    match = validate_pdf_identity(identity, text, "https://downloads.dell.com/dell-p2422h-monitor_users-guide.pdf")
    assert match.accepted is True
```

- [ ] **Step 2: Run focused tests and verify the Brother test fails for the expected reason**

Run: `pytest tests/test_pdf_identity_binding.py -v`
Expected before implementation: Brother sibling test fails because current validator accepts `brand_model`; existing tests remain green.

### Task 2: Implement narrow sibling-model URL conflict gate

**Files:**
- Modify: `src/product_intelligence/pdf_evidence.py`
- Test: `tests/test_pdf_identity_binding.py`

**Interfaces:**
- Produces: `_url_has_sibling_model_conflict(model: str | None, url: str) -> bool`
- `validate_pdf_identity()` returns `PdfIdentityMatch(False, 0.0, "sibling_model_url_conflict")` when the URL is explicitly tied to a sibling model.

- [ ] **Step 1: Add helpers**

```python
def _alpha_skeleton(value: str) -> str:
    return re.sub(r"[^a-z]", "", key_norm(value or ""))


def _url_has_sibling_model_conflict(model: str | None, url: str) -> bool:
    requested = _compact(model)
    if not requested or not any(ch.isdigit() for ch in requested):
        return False
    requested_skeleton = _alpha_skeleton(requested)
    if len(requested_skeleton) < 2:
        return False
    for token in re.findall(r"[a-z0-9-]{5,}", key_norm(url or "")):
        compact = _compact(token)
        if compact == requested or not any(ch.isdigit() for ch in compact):
            continue
        if _alpha_skeleton(compact) == requested_skeleton:
            return True
    return False
```

- [ ] **Step 2: Apply the gate before content-based acceptance**

```python
model = _compact(identity.model or identity.product_name)
if _url_has_sibling_model_conflict(identity.model or identity.product_name, url):
    return PdfIdentityMatch(False, 0.0, "sibling_model_url_conflict")
```

- [ ] **Step 3: Run focused tests**

Run: `pytest tests/test_pdf_identity_binding.py -v`
Expected: PASS.

- [ ] **Step 4: Trigger branch CI and source validation through the committed branch update**

Expected: CI and PDF smoke remain green; Source Validation must report zero cross-product contamination before release.
