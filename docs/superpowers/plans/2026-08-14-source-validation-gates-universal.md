# Universal Source Validation Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ProductIntelligence reject wrong/irrelevant sources before they can populate product data, while preserving useful exact web/PDF evidence and operating safely with OCR.space and Mistral disabled.

**Architecture:** Keep SEARCH/discovery independent from evidence acceptance. Introduce four focused deterministic modules—page type, identity gate, source authority, and evidence policy—and make `batch.py` orchestrate them without absorbing their logic. Extraction remains responsible for producing candidate evidence; the new policy layer decides whether each candidate source/evidence is allowed into the final `ProductRecord`.

**Tech Stack:** Python 3.12, Pydantic, requests, BeautifulSoup/lxml, extruct, PyMuPDF, Playwright/Chromium, pytest. Evaluate `trafilatura`/`selectolax` only if benchmarked improvements justify adding them.

## Global Constraints

- Base integration branch is `release/windows`; never modify `main`.
- Precision first / fail closed: unsupported or conflicting fields remain empty.
- No brand-specific product/domain rules in production code.
- No Serper or paid SERP dependency.
- OCR.space and Mistral remain OFF for the baseline benchmark and cannot rescue bad sources.
- Category/search/update/legal/account/generic-support pages may aid discovery but cannot contribute material technical fields.
- Strong-identifier conflicts always block material evidence.
- Hostname substring matching alone can never classify a source as manufacturer.
- Existing exact product/PDF flows must remain usable.
- Per-product research must stay bounded; no unbounded crawling/retries.

---

## File Structure

### New production modules

- `src/product_intelligence/page_type.py` — deterministic page/document classification and evidence permissions.
- `src/product_intelligence/identity_gate.py` — requested-vs-observed product identity assessment.
- `src/product_intelligence/source_authority.py` — source authority classification independent of identity.
- `src/product_intelligence/evidence_policy.py` — source/evidence admission, noise filtering, and cross-source consensus helpers.

### Existing production modules to modify

- `src/product_intelligence/pipeline.py` — surface page-level signals needed by the gates and apply source admission before returning material evidence.
- `src/product_intelligence/batch.py` — orchestrate the gates, reject bad sources explicitly, and emit decision trace counters.
- `src/product_intelligence/document_ingestion.py` — classify PDFs as `DOCUMENT`, attach extraction provenance, and keep native-PDF evidence compatible with the new policy.
- `src/product_intelligence/record_builder.py` — accept only policy-approved evidence and preserve conflicts/empty fields.
- `src/product_intelligence/models.py` — add compact typed decision metadata if equivalent types do not already exist.

### Tests

- `tests/test_page_type_gate.py`
- `tests/test_identity_gate.py`
- `tests/test_source_authority.py`
- `tests/test_evidence_policy.py`
- `tests/test_source_validation_pipeline.py`
- `tests/integration_source_validation_benchmark.py`
- Extend existing regression tests where the current public interface is already covered rather than duplicating them.

---

### Task 1: Page Type Gate

**Files:**
- Create: `src/product_intelligence/page_type.py`
- Test: `tests/test_page_type_gate.py`

**Interfaces:**
- Consumes: `url: str`, optional `content_type: str`, `title: str`, `h1: str`, structured-data types, counts/signals derived from parsed HTML.
- Produces: `PageTypeAssessment(page_type: str, confidence: float, reasons: tuple[str, ...], material_allowed: bool)`.
- Public function: `classify_page_type(signals: PageSignals) -> PageTypeAssessment`.

- [ ] **Step 1: Write failing tests for product vs non-material pages**

```python
from product_intelligence.page_type import PageSignals, classify_page_type


def test_product_jsonld_is_material():
    result = classify_page_type(PageSignals(
        url="https://example.com/products/widget-100",
        content_type="text/html",
        title="Widget 100",
        h1="Widget 100",
        schema_types=("Product",),
        product_entity_count=1,
        specification_block_count=1,
    ))
    assert result.page_type == "PRODUCT"
    assert result.material_allowed is True


def test_category_with_target_card_is_not_material():
    result = classify_page_type(PageSignals(
        url="https://example.com/headphones",
        content_type="text/html",
        title="All Headphones",
        h1="Headphones",
        schema_types=("ItemList", "BreadcrumbList"),
        product_entity_count=18,
        product_card_count=18,
    ))
    assert result.page_type == "CATEGORY"
    assert result.material_allowed is False


def test_update_page_is_not_material_even_on_official_domain():
    result = classify_page_type(PageSignals(
        url="https://brand.example/support/model-x/update",
        content_type="text/html",
        title="Software Update",
        h1="Notify Update",
        schema_types=("Article",),
        update_signal=True,
    ))
    assert result.page_type == "UPDATE"
    assert result.material_allowed is False
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_page_type_gate.py -q`

Expected: FAIL because `page_type.py`/types do not exist.

- [ ] **Step 3: Implement minimal deterministic classifier**

```python
from dataclasses import dataclass

MATERIAL_TYPES = {"PRODUCT", "PRODUCT_VARIANT", "DOCUMENT", "SUPPORT_PRODUCT"}

@dataclass(frozen=True)
class PageSignals:
    url: str
    content_type: str = ""
    title: str = ""
    h1: str = ""
    schema_types: tuple[str, ...] = ()
    product_entity_count: int = 0
    product_card_count: int = 0
    specification_block_count: int = 0
    update_signal: bool = False
    legal_signal: bool = False
    account_signal: bool = False
    generic_support_signal: bool = False

@dataclass(frozen=True)
class PageTypeAssessment:
    page_type: str
    confidence: float
    reasons: tuple[str, ...]
    material_allowed: bool


def classify_page_type(signals: PageSignals) -> PageTypeAssessment:
    # Order from strong negative page types to material types.
    ...
```

Implement only multi-signal generic rules: PDF MIME/path → `DOCUMENT`; explicit legal/account/update signals → corresponding non-material type; `ItemList`/many product cards → `CATEGORY`; a single structured `Product` plus product-level heading/spec block → `PRODUCT`; support path + single product + specs/downloads → `SUPPORT_PRODUCT`; otherwise `UNKNOWN`.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_page_type_gate.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/page_type.py tests/test_page_type_gate.py
git commit -m "feat: add deterministic page type gate"
```

---

### Task 2: Exact Identity Gate

**Files:**
- Create: `src/product_intelligence/identity_gate.py`
- Test: `tests/test_identity_gate.py`

**Interfaces:**
- Consumes: requested `ProductIdentity`; observed strong identifiers/model/name/brand extracted from a candidate source.
- Produces: `IdentityAssessment(status, confidence, reasons, matched_identifiers, conflicting_identifiers)` where status is one of `EXACT`, `COMPATIBLE`, `AMBIGUOUS`, `CONFLICT`, `INSUFFICIENT`.
- Public function: `assess_identity(requested: ProductIdentity, observed: ObservedIdentity) -> IdentityAssessment`.

- [ ] **Step 1: Write RED tests covering strong matches and contamination**

```python
from product_intelligence.identity_gate import ObservedIdentity, assess_identity
from product_intelligence.models import ProductIdentity


def test_exact_mpn_match_passes():
    result = assess_identity(
        ProductIdentity(brand="Brand", model="Model 22", mpn="ABC-22"),
        ObservedIdentity(brand="Brand", model="Model 22", mpns=("ABC-22",)),
    )
    assert result.status == "EXACT"


def test_different_dominant_model_blocks_even_same_brand():
    result = assess_identity(
        ProductIdentity(brand="Brand", model="Model 22"),
        ObservedIdentity(brand="Brand", model="Model 26 Ultra"),
    )
    assert result.status == "CONFLICT"


def test_conflicting_strong_identifier_blocks():
    result = assess_identity(
        ProductIdentity(mpn="ABC-22"),
        ObservedIdentity(mpns=("ABC-26",)),
    )
    assert result.status == "CONFLICT"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_identity_gate.py -q`

Expected: FAIL because module/interfaces do not exist.

- [ ] **Step 3: Implement normalization and assessment**

Implement:

```python
@dataclass(frozen=True)
class ObservedIdentity:
    brand: str | None = None
    model: str | None = None
    product_name: str | None = None
    mpns: tuple[str, ...] = ()
    gtins: tuple[str, ...] = ()
    eans: tuple[str, ...] = ()
    upcs: tuple[str, ...] = ()

@dataclass(frozen=True)
class IdentityAssessment:
    status: str
    confidence: float
    reasons: tuple[str, ...]
    matched_identifiers: tuple[str, ...] = ()
    conflicting_identifiers: tuple[str, ...] = ()
```

Rules:
- normalize punctuation/case for comparisons;
- exact MPN/GTIN/EAN/UPC match → `EXACT` unless any different observed strong ID conflicts;
- different observed strong ID → `CONFLICT`;
- same brand + exact normalized model/name without strong IDs → `COMPATIBLE`;
- clearly different dominant model under same brand → `CONFLICT`;
- family overlap only → `AMBIGUOUS`;
- insufficient product-level signals → `INSUFFICIENT`.

Crucially, never copy the requested model into `ObservedIdentity` before assessment.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_identity_gate.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/identity_gate.py tests/test_identity_gate.py
git commit -m "feat: add strong product identity gate"
```

---

### Task 3: Source Authority Without Brand-Substring False Positives

**Files:**
- Create: `src/product_intelligence/source_authority.py`
- Test: `tests/test_source_authority.py`

**Interfaces:**
- Consumes: URL/domain plus structured organization/canonical/site signals.
- Produces: `AuthorityAssessment(source_class, confidence, reasons)`.
- Public function: `classify_source_authority(signals: AuthoritySignals) -> AuthorityAssessment`.

- [ ] **Step 1: Write RED tests**

```python
from product_intelligence.source_authority import AuthoritySignals, classify_source_authority


def test_brand_token_in_hostname_is_not_manufacturer_by_itself():
    result = classify_source_authority(AuthoritySignals(
        url="https://brandfixpros.example/product/abc",
        requested_brand="Brand",
    ))
    assert result.source_class != "manufacturer"


def test_consistent_brand_owned_organization_signals_can_be_manufacturer():
    result = classify_source_authority(AuthoritySignals(
        url="https://www.brand.example/products/abc",
        requested_brand="Brand",
        organization_names=("Brand",),
        canonical_host="www.brand.example",
        same_origin_product_links=12,
        brand_owned_footer=True,
    ))
    assert result.source_class == "manufacturer"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_source_authority.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement evidence-based authority scoring**

Implement typed signals and require combinations of independent signals for `manufacturer`/`manufacturer_support`. A single hostname token, title token, or page keyword must never be enough. Provide lower-confidence classes `retailer`, `marketplace`, `technical_database`, `third_party`, `unknown` from deterministic page/site signals when present.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_source_authority.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/source_authority.py tests/test_source_authority.py
git commit -m "feat: classify source authority from independent signals"
```

---

### Task 4: Evidence Admission and Noise Rejection

**Files:**
- Create: `src/product_intelligence/evidence_policy.py`
- Test: `tests/test_evidence_policy.py`

**Interfaces:**
- Consumes: `Evidence`, `PageTypeAssessment`, `IdentityAssessment`, `AuthorityAssessment`, extraction method.
- Produces: `EvidenceDecision(allowed: bool, reason: str, confidence: float)`.
- Public functions: `decide_evidence(...)`, `is_noise_attribute(attribute: str) -> bool`.

- [ ] **Step 1: Write RED tests**

```python
from product_intelligence.evidence_policy import decide_evidence, is_noise_attribute


def test_category_page_evidence_is_blocked():
    decision = decide_evidence(
        page_type="CATEGORY",
        identity_status="EXACT",
        source_class="manufacturer",
        extraction_method="jsonld",
        semantic="color",
        confidence=.99,
    )
    assert decision.allowed is False
    assert decision.reason == "PAGE_TYPE_NOT_MATERIAL"


def test_noise_keys_are_rejected():
    assert is_noise_attribute("currencyCode")
    assert is_noise_attribute("user_authenticated")
    assert not is_noise_attribute("battery_capacity")


def test_identity_conflict_blocks_every_material_fact():
    decision = decide_evidence(
        page_type="PRODUCT",
        identity_status="CONFLICT",
        source_class="manufacturer",
        extraction_method="jsonld",
        semantic="battery_capacity",
        confidence=.99,
    )
    assert decision.allowed is False
    assert decision.reason == "IDENTITY_CONFLICT"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_evidence_policy.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement policy matrix**

Policy order:
1. block non-material page types;
2. block identity `CONFLICT`, `AMBIGUOUS`, `INSUFFICIENT` for material autofill;
3. block noise/telemetry semantics;
4. enforce extraction-method minimum confidence (`jsonld`/explicit spec table > cleaned DOM heuristic);
5. permit exact manufacturer/product/document evidence at lower corroboration burden;
6. mark lower-authority weak evidence as needing corroboration rather than accepting directly.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_evidence_policy.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/evidence_policy.py tests/test_evidence_policy.py
git commit -m "feat: enforce fail-closed evidence policy"
```

---

### Task 5: Surface Page Signals From Existing Extraction Pipeline

**Files:**
- Modify: `src/product_intelligence/pipeline.py`
- Modify if needed: existing HTML extraction/profile module(s) used by `ProductPipeline.process_url`
- Test: `tests/test_source_validation_pipeline.py`

**Interfaces:**
- Consumes existing fetch/parse results.
- Produces source decision metadata without changing `process_url(...)` caller semantics.
- Store decision metadata under `rec.fetch["source_decision"]` and/or `rec.evidence_graph["source_decision"]`.

- [ ] **Step 1: Write integration-style RED fixture tests**

Use local HTML fixtures, not live web:

```python
def test_category_fixture_does_not_return_material_specs(product_pipeline, category_fixture_url):
    rec = product_pipeline.process_url(
        ProductIdentity(brand="Acme", model="X100", mpn="ACME-X100"),
        category_fixture_url,
        browser_fallback=False,
    )
    assert rec.fetch["source_decision"]["page_type"] == "CATEGORY"
    assert rec.specifications == {}


def test_wrong_product_fixture_is_identity_conflict(product_pipeline, wrong_model_fixture_url):
    rec = product_pipeline.process_url(
        ProductIdentity(brand="Acme", model="X100"),
        wrong_model_fixture_url,
        browser_fallback=False,
    )
    assert rec.fetch["source_decision"]["identity"] == "CONFLICT"
    assert rec.evidence == []
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_source_validation_pipeline.py -q`

Expected: FAIL because pipeline does not expose/apply the new gates.

- [ ] **Step 3: Extract signals before record construction**

In `ProductPipeline.process_url`:
- parse structured data first;
- derive observed identifiers/model/name without seeding them from requested identity;
- derive `PageSignals` and `AuthoritySignals` from fetched/parsed content;
- classify page type, identity, authority;
- filter extracted evidence through `decide_evidence` before record building;
- preserve rejected reasons in audit metadata;
- do not raise merely because a source is non-material; return a record with no material evidence plus decision metadata so `batch.py` can reject it explicitly.

- [ ] **Step 4: Run focused GREEN**

Run: `python -m pytest tests/test_source_validation_pipeline.py -q`

Expected: PASS.

- [ ] **Step 5: Run existing pipeline tests**

Run: `python -m pytest tests -q -k "pipeline or identity or source or extractor"`

Expected: no new regressions.

- [ ] **Step 6: Commit**

```bash
git add src/product_intelligence/pipeline.py src/product_intelligence/*.py tests/test_source_validation_pipeline.py
git commit -m "feat: apply source validation gates before web evidence acceptance"
```

---

### Task 6: Preserve Native PDF Path Under the Same Policy

**Files:**
- Modify: `src/product_intelligence/document_ingestion.py`
- Test: extend `tests/test_source_validation_pipeline.py` or existing PDF ingestion tests.

**Interfaces:**
- PDF documents classify as `DOCUMENT`.
- Identity must still be assessed from document text/metadata/identifier signals.
- Existing native-text extraction remains authoritative; OCR/Mistral stay disabled in benchmark.

- [ ] **Step 1: Write RED tests**

```python
def test_exact_technical_pdf_can_contribute_material_evidence(pdf_fixture_exact):
    rec = process_pdf_document(
        ProductIdentity(mpn="ACME-X100", model="X100"),
        pdf_fixture_exact,
        target_semantics=["weight"],
    )
    assert rec.fetch["source_decision"]["page_type"] == "DOCUMENT"
    assert rec.evidence


def test_pdf_for_different_model_is_rejected(pdf_fixture_wrong_model):
    rec = process_pdf_document(
        ProductIdentity(model="X100"),
        pdf_fixture_wrong_model,
        target_semantics=["weight"],
    )
    assert rec.fetch["source_decision"]["identity"] == "CONFLICT"
    assert rec.evidence == []
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests -q -k "technical_pdf_can_contribute or pdf_for_different_model"`

Expected: FAIL until policy metadata/filtering exists in PDF ingestion.

- [ ] **Step 3: Apply document gate**

Attach `DOCUMENT` page type, build `ObservedIdentity` from native PDF text/metadata, assess identity, and pass extracted facts through evidence policy. Reject sentence fragments that fail structural/value sanity checks instead of treating them as model/interface values.

- [ ] **Step 4: Run GREEN plus existing PDF tests**

Run: `python -m pytest tests -q -k "pdf or document"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/document_ingestion.py tests
git commit -m "feat: enforce identity and evidence gates for PDFs"
```

---

### Task 7: Cross-Source Consensus and Fail-Closed Record Resolution

**Files:**
- Modify: `src/product_intelligence/evidence_policy.py`
- Modify: `src/product_intelligence/record_builder.py`
- Test: `tests/test_evidence_policy.py`

**Interfaces:**
- Public helper: `resolve_evidence_group(evidence_items, source_decisions) -> ConsensusDecision`.
- Outcome contains `accepted_value`, `status`, `reason`, and supporting/rejected evidence IDs/URLs.

- [ ] **Step 1: Write RED tests for conflict and corroboration**

```python
def test_two_strong_conflicting_sources_leave_field_empty():
    result = resolve_evidence_group([
        fact(value="5000", authority="manufacturer", identity="EXACT", confidence=.95),
        fact(value="6000", authority="manufacturer_support", identity="EXACT", confidence=.95),
    ])
    assert result.accepted_value is None
    assert result.reason == "SOURCE_CONFLICT"


def test_exact_manufacturer_single_source_can_win():
    result = resolve_evidence_group([
        fact(value="5000", authority="manufacturer", identity="EXACT", confidence=.95),
    ])
    assert result.accepted_value == "5000"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_evidence_policy.py -q`

Expected: FAIL for new consensus tests.

- [ ] **Step 3: Implement deterministic consensus ranking**

Precedence:
1. exact manufacturer product/document;
2. exact manufacturer support;
3. exact authorized distributor/technical database;
4. exact retailer;
5. exact third party.

Material conflict among strong independent sources → no accepted value. Lower-authority weak evidence requires corroboration. Record audit reason codes exactly as in the spec.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_evidence_policy.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/evidence_policy.py src/product_intelligence/record_builder.py tests/test_evidence_policy.py
git commit -m "feat: resolve product facts with fail-closed source consensus"
```

---

### Task 8: Batch Orchestration, Rejection Logs, and Counters

**Files:**
- Modify: `src/product_intelligence/batch.py`
- Test: `tests/test_source_validation_pipeline.py`

**Interfaces:**
- `scrape_item(...)` signature remains unchanged.
- A source with no admissible material evidence is not appended to `accepted` merely because fetch/identity parsing succeeded.
- Logs expose page type, identity, authority, evidence permission, and rejection reason.

- [ ] **Step 1: Write RED tests**

```python
def test_batch_rejects_non_material_source_even_when_requested_mpn_is_present(...):
    ...
    assert rec is None
    assert any("EVIDENCE_ALLOWED=NO reason=PAGE_TYPE_NOT_MATERIAL" in line for line in logs)


def test_batch_rejects_cross_model_source(...):
    ...
    assert rec is None
    assert any("IDENTITY=CONFLICT" in line for line in logs)
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_source_validation_pipeline.py -q`

Expected: FAIL until batch uses decision metadata.

- [ ] **Step 3: Replace acceptance condition in `scrape_item`**

After `pipe.process_url(...)`/`process_pdf_document(...)`, inspect `source_decision`:
- reject if page type is non-material;
- reject identity conflict/insufficient material identity;
- accept only if at least one policy-approved material evidence item remains;
- log compact decision lines;
- increment per-run counters through local audit metadata rather than global state.

Do not expand `batch.py` with classification algorithms; call the new modules.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_source_validation_pipeline.py -q`

Expected: PASS.

- [ ] **Step 5: Run full regression**

Run: `python -m pytest -q`

Expected: 0 failures.

- [ ] **Step 6: Commit**

```bash
git add src/product_intelligence/batch.py tests/test_source_validation_pipeline.py
git commit -m "feat: reject inadmissible sources in batch scraping"
```

---

### Task 9: Re-run the Six Known Failure/Success Cases Without OCR/Mistral

**Files:**
- Create: `tests/integration_source_validation_benchmark.py`
- Do not modify production logic in this task.

**Interfaces:**
- Uses real `scrape_item()`.
- Uses `SourceStrategy(web=True, pdf=True, ocr=False, mistral=False)` and `provider_run_scope` with both providers disabled.
- Writes JSON artifact `source-validation-benchmark.json`.

- [ ] **Step 1: Implement the diagnostic benchmark**

Include the previous six identities as regression probes, but assess generalized outputs:
- requested vs resolved identity;
- source page types;
- authority classes;
- material evidence count;
- rejection reasons;
- contamination detection;
- runtime;
- OCR/Mistral provider events.

The benchmark must explicitly assert:

```python
assert not forbidden_provider_events
assert cross_product_contamination_count == 0
assert false_manufacturer_count == 0
assert non_material_evidence_count == 0
```

- [ ] **Step 2: Run live six-case benchmark**

Run: `python tests/integration_source_validation_benchmark.py --set regression6`

Expected: process completes; any acceptance-gate violation returns non-zero and writes the artifact.

- [ ] **Step 3: Inspect every failure before changing thresholds**

Do not loosen gates merely to increase `SCRAPED`. Categorize each failure as discovery miss, access issue, correct fail-closed, or gate bug.

- [ ] **Step 4: Commit benchmark only after its assertions match the approved spec**

```bash
git add tests/integration_source_validation_benchmark.py
git commit -m "test: add live source validation regression benchmark"
```

---

### Task 10: Ten-Brand / Multi-Category Live Benchmark

**Files:**
- Modify: `tests/integration_source_validation_benchmark.py`
- Add workflow: `.github/workflows/source-validation-benchmark.yml`

**Interfaces:**
- Benchmark set `ten_brand` must contain at least 10 brands and materially different categories.
- Run with Web/PDF ON, OCR/Mistral OFF.

- [ ] **Step 1: Define the ten-brand corpus**

Select stable public product identities with strong identifiers where possible across:
- audio;
- mouse/peripheral;
- cable/accessory;
- smartphone;
- laptop;
- rugged phone;
- storage;
- networking;
- monitor/display;
- printer/accessory or another materially distinct category.

Do not put brand-specific behavior in production code; identities exist only in the diagnostic test corpus.

- [ ] **Step 2: Add GitHub Actions workflow**

```yaml
name: Source Validation Benchmark
on:
  workflow_dispatch:
  pull_request:
    paths:
      - 'src/product_intelligence/page_type.py'
      - 'src/product_intelligence/identity_gate.py'
      - 'src/product_intelligence/source_authority.py'
      - 'src/product_intelligence/evidence_policy.py'
      - 'src/product_intelligence/pipeline.py'
      - 'src/product_intelligence/batch.py'
      - 'src/product_intelligence/document_ingestion.py'
      - 'tests/integration_source_validation_benchmark.py'
      - '.github/workflows/source-validation-benchmark.yml'

jobs:
  benchmark:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -e '.[desktop,dev]'
      - run: playwright install chromium
      - run: python tests/integration_source_validation_benchmark.py --set ten_brand
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: source-validation-benchmark
          path: source-validation-benchmark.json
```

- [ ] **Step 3: Run benchmark and evaluate acceptance gates**

Required:
- cross-product contamination = 0 known cases;
- false manufacturer classification = 0 known cases;
- non-material page material evidence = 0;
- OCR/Mistral calls = 0;
- ≥80% products either produce validated material evidence or a precise fail-closed reason;
- no generic silent `no hubo candidatos` when discovery/gate telemetry exists;
- bounded runtime.

- [ ] **Step 4: Commit workflow/corpus**

```bash
git add tests/integration_source_validation_benchmark.py .github/workflows/source-validation-benchmark.yml
git commit -m "test: benchmark source validation across ten brands"
```

---

### Task 11: Optional Main-Content Parser Evaluation

**Files:**
- Potential modify: `pyproject.toml`
- Potential modify: existing extraction helper module
- Test: add focused benchmark tests only if needed.

**Interfaces:**
- This task is conditional. Do not add dependencies unless current extraction still leaks boilerplate after Tasks 1–10.

- [ ] **Step 1: Measure current boilerplate/noise failures from benchmark artifact**

If accepted material pages still emit recurring navigation/session/marketing fragments after policy filtering, proceed. Otherwise skip this task and record `NOT_NEEDED` in PR notes.

- [ ] **Step 2: Compare `trafilatura` and/or `selectolax` on representative fixtures**

Measure:
- useful spec extraction retained;
- noise reduced;
- runtime/memory impact;
- compatibility with packaged Windows build.

- [ ] **Step 3: Add only the library that gives measurable benefit**

If neither clearly improves benchmark metrics, add neither.

- [ ] **Step 4: Run full regression + benchmark again**

Run:

```bash
python -m pytest -q
python tests/integration_source_validation_benchmark.py --set regression6
python tests/integration_source_validation_benchmark.py --set ten_brand
```

Expected: no acceptance-gate regression.

---

### Task 12: Final Verification, Versioning, and Release Candidate

**Files:**
- Modify version sources only after all implementation/benchmark gates pass.
- Update release notes/changelog if the repository has an established path.

**Interfaces:**
- Release target remains `release/windows`.
- Do not merge benchmark-only temporary branches into `main`.

- [ ] **Step 1: Run fresh full regression**

Run: `python -m pytest -q`

Expected: 0 failures.

- [ ] **Step 2: Run fresh six-case benchmark with providers OFF**

Run: `python tests/integration_source_validation_benchmark.py --set regression6`

Expected: all hard source-safety gates pass.

- [ ] **Step 3: Run fresh ten-brand benchmark with providers OFF**

Run: `python tests/integration_source_validation_benchmark.py --set ten_brand`

Expected: all hard gates pass and ≥80% useful-evidence-or-explicit-fail-closed criterion passes.

- [ ] **Step 4: Verify no OCR/Mistral execution**

Artifact must contain:

```json
{
  "ocr_or_mistral_executed": false,
  "forbidden_provider_events": []
}
```

- [ ] **Step 5: Review benchmark deltas against the prior baseline**

Explicitly compare the known failure classes:
- category accepted as product;
- false manufacturer from hostname substring;
- update page accepted as technical source;
- cross-model contamination;
- exact native PDF usefulness;
- extraction noise.

- [ ] **Step 6: Only then bump the next patch version and open PR to `release/windows`**

PR body must include test run IDs/artifacts and known remaining limitations. Do not claim completion from unit tests alone.

- [ ] **Step 7: After merge, verify Windows Release workflow end-to-end**

Required steps: version consistency, regression tests, desktop smoke, bundled Chromium, PyInstaller, executable/resources verification, updater standalone, ZIP/SHA256, GitHub Release publication.

---

## Self-Review Against the Approved Spec

- Page type classification and non-material permissions: Tasks 1, 5, 8.
- Exact identity and cross-model conflict: Tasks 2, 5, 6, 8.
- Authority independent from brand substring: Task 3, integrated in Task 5.
- Structured extraction/noise filtering: Tasks 4, 5, optional Task 11.
- Native PDF preservation: Task 6.
- Consensus/fail-closed behavior: Task 7.
- Decision observability and counts: Task 8 plus benchmark artifacts.
- Six known regression scenarios: Task 9.
- Minimum ten-brand multi-category live test: Task 10.
- OCR/Mistral explicitly OFF: Tasks 9, 10, 12.
- No paid SERP dependency: preserved globally.
- No brand hardcoding in production: enforced globally; benchmark identities are test-only.
- Bounded research/runtime: Tasks 8, 10, 12.
- Full regression and Windows release gate: Task 12.

No unresolved placeholders or spec gaps remain in this plan.
