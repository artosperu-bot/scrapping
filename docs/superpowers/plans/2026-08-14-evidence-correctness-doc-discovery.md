# Evidence Correctness + Document Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mejorar la precisión semántica del pipeline, descubrir y validar documentación técnica oficial, y redactar descripciones con Mistral únicamente desde hechos canonical validados, sin degradar Scraping Excel, Multimedia, Price Intelligence, OCR.space, Configuración ni updater.

**Architecture:** Reforzar las capas existentes en lugar de crear un pipeline paralelo. `discovery.py` ampliará el descubrimiento documental; `canonical_facts.py` será la única fuente autorizada para resolver hechos; `resolution_engine.py` reutilizará canonical antes de declarar insuficiencia; `description_narrator.py` consumirá hechos canonical normalizados. Los módulos de UI siguen separados.

**Tech Stack:** Python 3.12, pytest, requests, BeautifulSoup/lxml, rapidfuzz, Mistral client existente, GitHub Actions Windows.

## Global Constraints

- Base de trabajo: `release/windows` @ `a80e98b3902124bee824d01d054100f8a88be419`.
- Rama de implementación: `feat/evidence-correctness-doc-discovery`.
- Nunca tocar `main`.
- No rehacer el sistema ni crear un pipeline paralelo.
- No modificar scraping general salvo evidencia de causa raíz en esa capa.
- No romper OCR.space, Mistral, PDF evidence, Multimedia, Price Intelligence, Configuración ni auto-updater.
- `UNKNOWN` nunca se convierte implícitamente en `Sí` o `No`.
- Una celda vacía es preferible a una clasificación no defendible.
- El canonical final es la única verdad autorizada para escribir atributos en Excel.
- Mistral redacta; no decide hechos técnicos.
- Scraping Excel, Multimedia y Price Intelligence permanecen separados en la interfaz.
- TDD obligatorio: RED real antes del cambio de producción, GREEN mínimo, regresión del módulo y suite completa antes de integrar.

---

## File Structure

**Modify**
- `src/product_intelligence/canonical_facts.py` — reglas conservadoras de conectividad, IP, identidad y unidades.
- `src/product_intelligence/resolution_engine.py` — canonical-first resolution y bloqueo de contradicciones.
- `src/product_intelligence/discovery.py` — generación de consultas documentales y ranking de candidatos PDF/manual/datasheet.
- `src/product_intelligence/description_narrator.py` — facts canonical-only, unidades, traducción de labels y deduplicación.
- `src/product_intelligence/source_authority.py` — solo si la autoridad documental existente no distingue oficial/manual/distribuidor; mantener interfaz actual.
- `src/product_intelligence/batch.py` — integrar document discovery únicamente en el punto donde ya se agregan evidencias, sin cambiar UX ni módulos.

**Create**
- `src/product_intelligence/document_discovery.py` — responsabilidad única: construir consultas documentales, clasificar tipo de documento y validar identidad antes de promoverlo a evidencia.

**Tests**
- `tests/test_canonical_semantic_regressions.py`
- `tests/test_feature_positive_evidence.py`
- `tests/test_resolution_engine.py` o el test equivalente existente de resolución.
- `tests/test_document_discovery.py`
- `tests/test_description_narrator.py`
- `tests/test_jbl_correctness_regression.py` — fixture/regresión de los tres JBL sin lógica específica por SKU en producción.

---

### Task 1: Freeze Current Wins and Reproduce the JBL Semantic Failures

**Files:**
- Modify: `tests/test_canonical_semantic_regressions.py`
- Modify: `tests/test_feature_positive_evidence.py`
- Create: `tests/test_jbl_correctness_regression.py`

**Interfaces:**
- Consumes: `build_canonical_facts(rec) -> dict[str, Any]`, `analyze_resolution(rec, template_plan) -> dict[str, Any]`.
- Produces: executable regression contracts for UNKNOWN, RF, wired USB, IP, autonomy and identity reuse.

- [ ] **Step 1: Add RED test for UNKNOWN Bluetooth**

```python
def test_quantum350_unknown_bluetooth_does_not_become_true(record_factory):
    rec = record_factory(
        evidence=[("Speakers", "Bluetooth", 0.90)],
    )
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["bluetooth"]["present"] is None
```

The fixture must model the real defect class: an unrelated attribute/value containing a Bluetooth-looking token must not establish positive presence.

- [ ] **Step 2: Add RED test for Bluetooth 2.4 GHz != proprietary RF**

```python
def test_bluetooth_frequency_does_not_create_proprietary_rf(record_factory):
    rec = record_factory(evidence=[("Bluetooth transmission frequency", "2.4 GHz", 0.95)])
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["rf_2_4ghz"] is False
```

- [ ] **Step 3: Add RED test for charging USB != wired audio**

```python
def test_charging_usb_c_does_not_create_wired_audio(record_factory):
    rec = record_factory(evidence=[("Charging cable", "USB-C", 0.95)])
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["wired"] is None
    assert facts["connectivity"]["usb_c"] is False
```

- [ ] **Step 4: Add RED test for canonical identity reuse**

```python
def test_gtin_brand_model_canonical_resolve_before_insufficient(record_factory):
    rec = record_factory(identity={"brand": "JBL", "model": "JBLT530CBLKAM", "gtin": "050036416887"})
    plan = {"scrape_semantics": ["Marca", "Modelo", "Código de barras"]}
    result = analyze_resolution(rec, plan)
    by_name = {row["semantic"]: row for row in result["fields"]}
    assert by_name["Marca"]["status"] != INSUFFICIENT_EVIDENCE
    assert by_name["Modelo"]["status"] != INSUFFICIENT_EVIDENCE
    assert by_name["Código de barras"]["status"] == FOUND_DIRECT
```

- [ ] **Step 5: Add GREEN-preservation tests for existing wins**

```python
def test_tune530c_usb_c_wired_stays_supported(record_factory):
    rec = record_factory(evidence=[("Connectivity", "USB-C wired", 0.95)])
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["usb_c"] is True
    assert facts["connectivity"]["wired"] is True
```

- [ ] **Step 6: Run targeted tests and confirm expected RED only**

Run:
```bash
pytest tests/test_canonical_semantic_regressions.py tests/test_feature_positive_evidence.py tests/test_jbl_correctness_regression.py -q
```
Expected: the newly added defect tests fail for the intended semantic reasons; existing preservation tests stay green.

- [ ] **Step 7: Commit RED tests**

```bash
git add tests/test_canonical_semantic_regressions.py tests/test_feature_positive_evidence.py tests/test_jbl_correctness_regression.py
git commit -m "test: reproduce JBL semantic correctness regressions"
```

---

### Task 2: Make Canonical Connectivity Conservative and Identity-Aware

**Files:**
- Modify: `src/product_intelligence/canonical_facts.py`
- Modify: `src/product_intelligence/resolution_engine.py`
- Test: files from Task 1

**Interfaces:**
- Consumes: filtered `ProductRecord.evidence` and `ProductRecord.identity`.
- Produces: canonical connectivity where positive/negative/unknown are explicit and `analyze_resolution()` prefers valid canonical identity.

- [ ] **Step 1: Add an explicit proprietary-RF detector**

Implement in `canonical_facts.py`:

```python
def _proprietary_rf_context(attribute: str, raw: str) -> bool:
    joined = key_norm(f"{attribute} {raw}")
    if "bluetooth" in joined and not re.search(r"dongle|receiver|receptor|wireless adapter|adaptador|proprietary|propietari|usb wireless", joined, re.I):
        return False
    return bool(re.search(r"\b(?:rf|radio ?frequency|2[ .]?4\s*ghz)\b", joined, re.I))
```

Then replace the broad `2.4 GHz` RF assignment with this function.

- [ ] **Step 2: Keep USB transport separate from accessory/charging context**

Use existing `_host_connectivity_attribute()` and `_charging_or_accessory_context()` so only a host/audio connectivity attribute can set `usb`/`usb_c` and contribute to `wired=True`.

- [ ] **Step 3: Remove implicit negative inference from absence**

In any connectivity branch that currently sets `wired=False` or equivalent solely because another transport was observed, keep `wired=None` unless there is explicit negative evidence for wired capability.

- [ ] **Step 4: Extend canonical resolver for identity fields**

Add to `_canonical_resolves()` in `resolution_engine.py`:

```python
if any(x in s for x in ["marca", "brand"]):
    if facts.get("identity", {}).get("brand"):
        return True, FOUND_DIRECT, "canonical_brand"
if any(x in s for x in ["modelo", "model", "mpn"]):
    if facts.get("identity", {}).get("model") or facts.get("identity", {}).get("mpn"):
        return True, FOUND_DIRECT, "canonical_model_or_mpn"
```

Keep GTIN logic already present.

- [ ] **Step 5: Make canonical resolution run before generic direct matching when direct evidence is weaker/ambiguous**

In `analyze_resolution()`, order decisions so `NOT_APPLICABLE` stays first, then trusted canonical facts, then generic fuzzy direct evidence. This prevents a weak secondary evidence row from overriding a stronger resolved fact.

- [ ] **Step 6: Run targeted tests**

```bash
pytest tests/test_canonical_semantic_regressions.py tests/test_feature_positive_evidence.py tests/test_jbl_correctness_regression.py -q
```
Expected: PASS.

- [ ] **Step 7: Run canonical/resolution regression slice**

```bash
pytest tests/test_canonical_facts_generic.py tests/test_canonical_semantic_regressions.py tests/test_generic_product_contracts.py -q
```
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/product_intelligence/canonical_facts.py src/product_intelligence/resolution_engine.py tests/
git commit -m "fix: make canonical connectivity and identity resolution conservative"
```

---

### Task 3: Resolve IP and Runtime Conflicts by Authority Instead of Last-Value-Wins

**Files:**
- Modify: `src/product_intelligence/canonical_facts.py`
- Modify: `src/product_intelligence/source_authority.py` only if needed to expose existing authority score consistently.
- Modify: `src/product_intelligence/resolution_engine.py`
- Test: `tests/test_jbl_correctness_regression.py`

**Interfaces:**
- Consumes: evidence rows with confidence/source metadata.
- Produces: one canonical IP/runtime only when evidence is defendible; unresolved conflicts remain blocked.

- [ ] **Step 1: Add RED test for conflicting IP evidence**

```python
def test_ip_conflict_does_not_use_last_value_seen(record_factory):
    rec = record_factory(evidence=[
        ("IP rating", "IPX5", 0.80, "retailer"),
        ("Ingress Protection", "IP65", 0.95, "official_manual"),
    ])
    facts = build_canonical_facts(rec)
    assert facts["durability"]["ip_rating"] == "IP65"
```

- [ ] **Step 2: Add RED test for runtime written while resolution says insufficient**

```python
def test_runtime_requires_canonical_resolution(record_factory):
    rec = record_factory(evidence=[("Battery life", "25", 0.55)])
    plan = {"scrape_semantics": ["Autonomía"]}
    result = analyze_resolution(rec, plan)
    row = result["fields"][0]
    assert row["status"] == INSUFFICIENT_EVIDENCE
    assert result["canonical_facts"]["battery"]["runtime_hours"] is None
```

- [ ] **Step 3: Introduce evidence selection helper inside canonical_facts**

Implement a small local selector that scores only candidate evidence for the same canonical field using existing confidence/source authority and chooses a winner only when one is strictly stronger; otherwise preserve `None`/conflict.

- [ ] **Step 4: Apply helper to IP and runtime only**

Do not generalize all attributes in this task. YAGNI: restrict to the observed conflict families.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_jbl_correctness_regression.py tests/test_canonical_semantic_regressions.py -q
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/product_intelligence/canonical_facts.py src/product_intelligence/source_authority.py src/product_intelligence/resolution_engine.py tests/test_jbl_correctness_regression.py
git commit -m "fix: resolve IP and runtime conflicts by evidence authority"
```

---

### Task 4: Add Official Document Discovery Without Broadening General Scraping

**Files:**
- Create: `src/product_intelligence/document_discovery.py`
- Modify: `src/product_intelligence/discovery.py`
- Modify: `src/product_intelligence/batch.py`
- Test: `tests/test_document_discovery.py`

**Interfaces:**
- Consumes: `ProductIdentity`, existing `search_web_query(identity, query, ...)`, candidate URLs.
- Produces:
  - `build_document_queries(identity: ProductIdentity) -> list[str]`
  - `classify_document_candidate(url: str, title: str, snippet: str) -> str | None`
  - `identity_matches_document(identity: ProductIdentity, url: str, title: str, snippet: str) -> bool`
  - `discover_product_documents(identity: ProductIdentity, *, limit: int = 8, timeout: int = 15) -> list[SearchCandidate]`

- [ ] **Step 1: Write query-generation tests**

```python
def test_document_queries_use_identity_and_document_intent():
    identity = ProductIdentity(brand="JBL", model="Quantum 350", mpn="JBLQ350WLBLK")
    queries = build_document_queries(identity)
    joined = "\n".join(queries).lower()
    assert "jbl" in joined
    assert "quantum 350" in joined or "jblq350wlblk" in joined
    assert "manual" in joined
    assert "datasheet" in joined
    assert "pdf" in joined
```

- [ ] **Step 2: Write identity rejection test**

```python
def test_document_candidate_for_different_model_is_rejected():
    identity = ProductIdentity(brand="JBL", model="Quantum 350", mpn="JBLQ350WLBLK")
    assert identity_matches_document(
        identity,
        "https://example.com/jbl-quantum-810-manual.pdf",
        "JBL Quantum 810 Owner's Manual",
        "Manual for Quantum 810",
    ) is False
```

- [ ] **Step 3: Verify RED**

```bash
pytest tests/test_document_discovery.py -q
```
Expected: import/function failures because module does not exist yet.

- [ ] **Step 4: Implement query generation**

Generate deduplicated queries from strong identity in this priority:

```text
"<brand> <model>" manual pdf
"<brand> <model>" datasheet pdf
"<brand> <model>" specifications pdf
"<brand> <model>" user manual
"<mpn>" manual pdf
"<mpn>" datasheet
```

Only include queries whose identity parts exist.

- [ ] **Step 5: Implement candidate classification**

Classify as one of `manual`, `datasheet`, `quick_start`, `compliance`, `technical_pdf`, or `None` using title/snippet/path tokens. A `.pdf` URL alone is not enough to promote identity.

- [ ] **Step 6: Implement identity validation**

Require a strong identifier match (`mpn/gtin/ean/upc`) OR brand + descriptive model match. Reject obvious conflicting model numbers in title/path.

- [ ] **Step 7: Implement discovery using existing providers**

`discover_product_documents()` must call `search_web_query()` for the controlled document queries, deduplicate URLs, retain only classified + identity-valid candidates, and rank official-looking host/support/manual URLs first. Do not add a new search provider.

- [ ] **Step 8: Integrate into batch at the existing evidence-enrichment point**

In `batch.py`, after base identity is known and before final resolution, call document discovery only when:
- identity has brand + model or a strong identifier; and
- unresolved technical semantics remain or no high-authority technical evidence exists.

Document content must enter the same existing PDF/evidence ingestion path. Do not write Excel directly from `document_discovery.py`.

- [ ] **Step 9: Run tests**

```bash
pytest tests/test_document_discovery.py tests/test_extraction_strategy.py tests/test_batch_orchestration_regressions.py -q
```
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add src/product_intelligence/document_discovery.py src/product_intelligence/discovery.py src/product_intelligence/batch.py tests/test_document_discovery.py
git commit -m "feat: discover identity-validated product manuals and datasheets"
```

---

### Task 5: Make Mistral Narration Canonical-Only and Unit-Safe

**Files:**
- Modify: `src/product_intelligence/description_narrator.py`
- Test: `tests/test_description_narrator.py`

**Interfaces:**
- Consumes: `build_canonical_facts(rec)`.
- Produces: `build_safe_facts(rec)` derived from canonical facts only, preserving unit-bearing values and excluding unknown facts.

- [ ] **Step 1: Add RED test that raw conflicting evidence is not narrated**

```python
def test_safe_facts_ignore_raw_evidence_when_canonical_is_unknown(record_factory):
    rec = record_factory(evidence=[("Bluetooth", "Speakers", 0.95)])
    facts = build_safe_facts(rec)
    assert not any("bluetooth" in item.lower() for item in facts)
```

- [ ] **Step 2: Add RED test for unit normalization**

```python
def test_safe_facts_preserve_driver_and_weight_units(record_factory):
    rec = record_factory(evidence=[("Driver size", "40 mm", 0.95), ("Weight", "252 g", 0.95)])
    facts = build_safe_facts(rec)
    text = " ".join(facts)
    assert "40 mm" in text
    assert "252 g" in text
```

- [ ] **Step 3: Replace evidence iteration with canonical projection**

Import `build_canonical_facts` and project only known fields into human-readable Spanish labels. Example projection:

```python
("Tamaño del driver", facts.get("driver_size_mm"), "mm")
("Peso", facts.get("product", {}).get("weight_g"), "g")
("Autonomía", facts.get("battery", {}).get("runtime_hours"), "h")
```

For booleans, emit only explicit `True` or `False`; never emit `None`.

- [ ] **Step 4: Deduplicate translated labels**

Use normalized Spanish label + normalized value as the dedupe key. Do not expose internal English attribute names such as `Charging Cable Length` when a normalized canonical Spanish label exists.

- [ ] **Step 5: Keep DescriptionGuard as fail-closed gate**

Do not relax number/risky-claim checks. Update allowed facts only as needed for normalized units.

- [ ] **Step 6: Run narrator tests**

```bash
pytest tests/test_description_narrator.py -q
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/product_intelligence/description_narrator.py tests/test_description_narrator.py
git commit -m "fix: ground Mistral descriptions in canonical normalized facts"
```

---

### Task 6: End-to-End Correctness Gate and Non-Regression

**Files:**
- Modify: `tests/test_jbl_correctness_regression.py`
- Modify: `.github/workflows/ci.yml` only if current suite does not already execute these tests automatically.

**Interfaces:**
- Consumes: all implementations from Tasks 2–5.
- Produces: one regression gate proving targeted defects are fixed while existing features remain green.

- [ ] **Step 1: Add a consolidated three-product contract**

The JBL regression test must assert:

```text
Quantum 350:
- bluetooth.present remains UNKNOWN without explicit positive evidence
- no RF from Bluetooth-frequency-only evidence
- no wired audio from charging cable only
- brand can resolve from canonical identity when valid

Endurance Run 3:
- Bluetooth 2.4 GHz does not create proprietary RF
- IP written value equals canonical selected IP
- runtime is not written when canonical cannot support it

Tune 530C:
- UNKNOWN Bluetooth does not become No
- GTIN/brand/model canonical resolve before insufficient
- USB-C wired remains supported
```

- [ ] **Step 2: Add a non-headphone generalization test**

Use an existing fixture from another category (phone, laptop or speaker already present in tests) and assert document discovery and canonical resolution do not introduce RF/wired/Bluetooth artifacts unrelated to that product.

- [ ] **Step 3: Run focused suite**

```bash
pytest tests/test_jbl_correctness_regression.py tests/test_document_discovery.py tests/test_description_narrator.py -q
```
Expected: PASS.

- [ ] **Step 4: Run full suite**

```bash
pytest -q
```
Expected: PASS with zero regressions.

- [ ] **Step 5: Verify capability registry**

Run the same optional capability check used by `.github/workflows/ci.yml`.
Expected: PASS.

- [ ] **Step 6: Commit final regression gate**

```bash
git add tests/test_jbl_correctness_regression.py .github/workflows/ci.yml
git commit -m "test: gate evidence correctness and document discovery regressions"
```

---

## Final Integration Gate

Before opening/merging the PR:

```bash
pytest -q
```
Expected: all tests PASS.

Then verify:

```text
UNKNOWN→Sí/No = 0 in regression fixtures
Bluetooth-frequency→proprietary-RF = 0
charging-USB→wired-audio = 0
Excel/canonical contradiction cases = 0
canonical GTIN/brand/model lost before resolver = 0
Mistral unsupported numbers/claims accepted = 0
JBL regression = PASS
non-headphone regression = PASS
full suite = PASS
```

Open a PR from `feat/evidence-correctness-doc-discovery` to `release/windows`. Do not target `main`. Do not publish a Windows release until the PR is reviewed and its CI is green.
