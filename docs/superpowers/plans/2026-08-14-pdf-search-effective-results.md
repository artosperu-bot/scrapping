# Effective PDF Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Solo PDF perform real Part Number-first document search with a Playwright/Chromium fallback, download and validate real PDFs, expose each stage in logs/UI, and preserve provider credentials across updates.

**Architecture:** Keep the current lightweight HTTP search as the fast path, but add a browser-backed search adapter that is invoked whenever HTTP discovery produces no usable document candidates. HTML search/product/support pages are discovery bridges only; final Solo PDF evidence must be a downloaded, identity-validated PDF before OCR.space or Mistral are called.

**Tech Stack:** Python 3, requests, BeautifulSoup/lxml, Playwright Chromium already bundled in the Windows desktop profile, Tkinter desktop UI, keyring, pytest, GitHub Actions, PyInstaller.

## Global Constraints

- Base all implementation work on `release/windows`; do not touch `main`.
- Do not add Serper or any paid SERP dependency.
- Part Number/MPN remains the preferred search identity; GTIN/EAN/UPC are secondary strong identifiers.
- `WEB=OFF | PDF=ON` may open HTML only as a discovery bridge; HTML cannot become final evidence.
- Do not modify OCR.space or Mistral extraction semantics until an accepted PDF exists.
- Do not expose API keys in logs, audit, Excel, settings.json, or test output.
- Preserve current Multimedia, Price Intelligence, general Web/HTML scraping, updater flow, and workspace behavior.
- Provider credentials remain in OS keyring service `ProductIntelligence`; non-secret settings remain in `%LOCALAPPDATA%\ProductIntelligence\settings.json`.

---

### Task 1: Add an explicit PDF search trace model

**Files:**
- Create: `src/product_intelligence/pdf_search_trace.py`
- Modify: `src/product_intelligence/document_discovery.py`
- Test: `tests/test_pdf_search_trace.py`

**Interfaces:**
- Produces: `PdfSearchTrace` dataclass with counters and `emit(event: str, **data) -> None`.
- Consumed by later search, landing-page, and download tasks.

- [ ] **Step 1: Write the failing test**

```python
from product_intelligence.pdf_search_trace import PdfSearchTrace


def test_pdf_search_trace_tracks_queries_results_and_downloads():
    trace = PdfSearchTrace(product_key="JBLQ350WLBLKAM")
    trace.emit("PDF_SEARCH_QUERY", query="JBLQ350WLBLKAM pdf", transport="http")
    trace.emit("PDF_SEARCH_HTTP_RESULT", result_count=0)
    trace.emit("PDF_SEARCH_BROWSER_RESULT", result_count=8)
    trace.emit("PDF_LINK_DISCOVERED", url="https://example.com/spec.pdf")
    trace.emit("PDF_DOWNLOAD_OK", url="https://example.com/spec.pdf", bytes=1200)

    summary = trace.summary()
    assert summary["queries"] == 1
    assert summary["browser_results"] == 8
    assert summary["pdf_links"] == 1
    assert summary["downloads_ok"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pdf_search_trace.py -v`

Expected: FAIL because `pdf_search_trace` does not exist.

- [ ] **Step 3: Implement minimal trace model**

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PdfSearchTrace:
    product_key: str
    events: list[dict] = field(default_factory=list)

    def emit(self, event: str, **data) -> None:
        self.events.append({"event": event, **data})

    def summary(self) -> dict[str, int]:
        total = lambda name, key="result_count": sum(
            int(row.get(key, 0) or 0) for row in self.events if row.get("event") == name
        )
        return {
            "queries": sum(1 for row in self.events if row.get("event") == "PDF_SEARCH_QUERY"),
            "http_results": total("PDF_SEARCH_HTTP_RESULT"),
            "browser_results": total("PDF_SEARCH_BROWSER_RESULT"),
            "landing_pages": sum(1 for row in self.events if row.get("event") == "PDF_LANDING_INSPECTED"),
            "pdf_links": sum(1 for row in self.events if row.get("event") == "PDF_LINK_DISCOVERED"),
            "downloads_ok": sum(1 for row in self.events if row.get("event") == "PDF_DOWNLOAD_OK"),
            "downloads_rejected": sum(1 for row in self.events if row.get("event") == "PDF_DOWNLOAD_REJECTED"),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pdf_search_trace.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/pdf_search_trace.py tests/test_pdf_search_trace.py
git commit -m "feat: add PDF search trace model"
```

---

### Task 2: Make Part Number-first PDF queries human-verifiable

**Files:**
- Modify: `src/product_intelligence/document_discovery.py`
- Test: `tests/test_document_discovery.py`

**Interfaces:**
- Consumes: `ProductIdentity`.
- Produces: `build_document_queries(identity) -> list[str]` beginning with `<strong-id> pdf` when a strong identifier exists.

- [ ] **Step 1: Write the failing test**

```python
from product_intelligence.document_discovery import build_document_queries
from product_intelligence.models import ProductIdentity


def test_part_number_pdf_query_is_first_and_human_verifiable():
    identity = ProductIdentity(mpn="JBLQ350WLBLKAM", model="JBLQ350WLBLKAM")
    queries = build_document_queries(identity)
    assert queries[0] == "JBLQ350WLBLKAM pdf"
    assert '"JBLQ350WLBLKAM" pdf' in queries
    assert '"JBLQ350WLBLKAM" filetype:pdf' in queries
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_document_discovery.py::test_part_number_pdf_query_is_first_and_human_verifiable -v`

Expected: FAIL because current first query is quoted-only.

- [ ] **Step 3: Update the query builder**

Implement this strong-ID ordering:

```python
queries.extend([
    f"{strong} pdf",
    f'"{strong}" pdf',
    f'"{strong}" filetype:pdf',
    f'"{strong}" manual pdf',
    f'"{strong}" datasheet pdf',
    f'"{strong}" spec sheet pdf',
    f'"{strong}" support downloads',
])
```

Keep brand/model variants after the strong-ID group.

- [ ] **Step 4: Run document discovery tests**

Run: `pytest tests/test_document_discovery.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/document_discovery.py tests/test_document_discovery.py
git commit -m "fix: prioritize human-verifiable PDF queries"
```

---

### Task 3: Add a browser-backed search adapter

**Files:**
- Create: `src/product_intelligence/browser_search.py`
- Test: `tests/test_browser_search.py`

**Interfaces:**
- Produces: `browser_search(query: str, *, timeout: int = 20, limit: int = 20) -> list[tuple[str, str, str]]`.
- Returns `(url, title, snippet)` tuples compatible with `_rank_candidates`.
- Must never return search-provider URLs.

- [ ] **Step 1: Write the failing unit test using a fake Playwright page**

```python
from product_intelligence.browser_search import _extract_result_rows


def test_extract_result_rows_returns_external_links_only():
    rows = _extract_result_rows([
        {"href": "https://www.jbl.com/JBLQ350WLBLKAM.html", "text": "JBL Quantum 350", "snippet": "Official JBL"},
        {"href": "https://www.bing.com/search?q=x", "text": "Bing", "snippet": ""},
        {"href": "https://support.jbl.com/manual.pdf", "text": "Manual PDF", "snippet": "PDF"},
    ])
    assert [row[0] for row in rows] == [
        "https://www.jbl.com/JBLQ350WLBLKAM.html",
        "https://support.jbl.com/manual.pdf",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_browser_search.py -v`

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement the Playwright adapter**

Use synchronous Playwright so the discovery layer remains synchronous:

```python
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse

SEARCH_HOSTS = {"bing.com", "www.bing.com"}


def _extract_result_rows(raw_rows):
    out = []
    seen = set()
    for row in raw_rows:
        url = str(row.get("href") or "").strip()
        if not url.startswith("http") or url in seen:
            continue
        host = (urlparse(url).hostname or "").lower()
        if host in SEARCH_HOSTS:
            continue
        seen.add(url)
        out.append((url, str(row.get("text") or ""), str(row.get("snippet") or "")))
    return out


def browser_search(query: str, *, timeout: int = 20, limit: int = 20):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/151 Safari/537.36"
            ))
            page.goto(
                f"https://www.bing.com/search?q={quote_plus(query)}&count={max(10, limit)}",
                wait_until="domcontentloaded",
                timeout=timeout * 1000,
            )
            raw = page.locator("li.b_algo").evaluate_all(
                """els => els.map(el => {
                  const a = el.querySelector('h2 a');
                  const p = el.querySelector('.b_caption p');
                  return {href: a?.href || '', text: a?.innerText || '', snippet: p?.innerText || ''};
                })"""
            )
            return _extract_result_rows(raw)[:limit]
        finally:
            browser.close()
```

Import `quote_plus` from `urllib.parse`.

- [ ] **Step 4: Run browser-search unit tests**

Run: `pytest tests/test_browser_search.py -v`

Expected: PASS without network because extraction is unit-tested separately.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/browser_search.py tests/test_browser_search.py
git commit -m "feat: add Chromium search fallback adapter"
```

---

### Task 4: Invoke browser search only when HTTP discovery is ineffective

**Files:**
- Modify: `src/product_intelligence/document_discovery.py`
- Test: `tests/test_document_discovery.py`

**Interfaces:**
- Consumes: `browser_search`, `_rank_candidates`, `PdfSearchTrace`.
- Produces: browser fallback only after an HTTP query yields zero useful candidates or the entire HTTP pass yields no resolvable PDFs.

- [ ] **Step 1: Write the failing fallback test**

```python
def test_document_discovery_uses_browser_when_http_returns_zero(monkeypatch):
    identity = ProductIdentity(mpn="JBLQ350WLBLKAM", model="JBLQ350WLBLKAM")
    monkeypatch.setattr(
        "product_intelligence.document_discovery._provider_search",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "product_intelligence.document_discovery.browser_search",
        lambda query, **kwargs: [
            (
                "https://www.jbl.com/JBLQ350WLBLKAM.html",
                "JBL Quantum 350",
                "Documents & Downloads",
            )
        ],
    )
    monkeypatch.setattr(
        "product_intelligence.document_discovery.resolve_document_candidate_urls",
        lambda identity, candidate, timeout=15: [
            SearchCandidate(
                "https://support.jbl.com/JBLQ350WLBLKAM-spec.pdf",
                "Spec Sheet",
                "JBLQ350WLBLKAM",
                .9,
                True,
            )
        ],
    )

    docs = discover_product_documents(identity, limit=4, timeout=1)
    assert docs
    assert docs[0].url.endswith(".pdf")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_document_discovery.py::test_document_discovery_uses_browser_when_http_returns_zero -v`

Expected: FAIL because browser fallback is not wired.

- [ ] **Step 3: Wire browser fallback into document discovery**

Add a helper:

```python
def _search_query_with_fallback(identity, query, *, limit, timeout, trace=None):
    if trace:
        trace.emit("PDF_SEARCH_QUERY", query=query, transport="http")
    http_rows = _provider_search(query, timeout)
    if trace:
        trace.emit("PDF_SEARCH_HTTP_RESULT", query=query, result_count=len(http_rows))
    ranked = _rank_candidates(http_rows, identity, limit)
    if ranked:
        return ranked

    if trace:
        trace.emit("PDF_SEARCH_BROWSER_FALLBACK", query=query)
    browser_rows = browser_search(query, timeout=max(timeout, 15), limit=max(limit * 2, 12))
    if trace:
        trace.emit("PDF_SEARCH_BROWSER_RESULT", query=query, result_count=len(browser_rows))
    return _rank_candidates(browser_rows, identity, limit)
```

Use this helper inside `discover_product_documents` instead of directly calling `_provider_search` for PDF document queries.

- [ ] **Step 4: Run document discovery tests**

Run: `pytest tests/test_document_discovery.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/document_discovery.py tests/test_document_discovery.py
git commit -m "fix: use browser fallback for PDF discovery"
```

---

### Task 5: Separate landing-page inspection from PDF acceptance

**Files:**
- Modify: `src/product_intelligence/document_discovery.py`
- Test: `tests/test_document_discovery.py`

**Interfaces:**
- `resolve_document_candidate_urls(...)` may fetch HTML landing pages but must return only direct PDFs.
- Emits `PDF_LANDING_INSPECTED` and `PDF_LINK_DISCOVERED` when a trace is supplied.

- [ ] **Step 1: Add failing trace test**

```python
def test_landing_page_only_emits_pdf_links(monkeypatch):
    identity = ProductIdentity(mpn="JBLT530CBLKAM")
    landing = SearchCandidate(
        "https://www.jbl.com/JBLT530CBLKAM.html",
        "JBL Tune 530C",
        "Documents & Downloads",
        .9,
        True,
    )

    class Response:
        text = '<a href="/manual.html">HTML</a><a href="/docs/spec.pdf">Spec PDF</a>'
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "product_intelligence.document_discovery.requests.get",
        lambda *a, **k: Response(),
    )

    rows = resolve_document_candidate_urls(identity, landing, timeout=1)
    assert [row.url for row in rows] == ["https://www.jbl.com/docs/spec.pdf"]
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `pytest tests/test_document_discovery.py::test_landing_page_only_emits_pdf_links -v`

Expected: PASS if existing behavior already satisfies this; if so, keep implementation and only add trace emission in Step 3.

- [ ] **Step 3: Add trace emission without changing acceptance**

Extend signature:

```python
def resolve_document_candidate_urls(identity, candidate, *, timeout=15, trace=None):
```

Emit landing inspection before `requests.get`, and emit each concrete PDF after `discover_pdf_candidates`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_document_discovery.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/document_discovery.py tests/test_document_discovery.py
git commit -m "feat: trace PDF landing discovery"
```

---

### Task 6: Download PDFs with protocol-level validation before ingestion

**Files:**
- Create: `src/product_intelligence/pdf_download.py`
- Modify: `src/product_intelligence/document_ingestion.py`
- Test: `tests/test_pdf_download.py`

**Interfaces:**
- Produces: `DownloadedPdf(path: Path, source_url: str, final_url: str, content_type: str, size_bytes: int, sha256: str)`.
- Produces: `download_pdf(url: str, destination_dir: Path, *, timeout: int = 20, trace=None) -> DownloadedPdf`.

- [ ] **Step 1: Write failing validation tests**

```python
import pytest
from product_intelligence.pdf_download import download_pdf


def test_rejects_html_response_even_when_url_looks_like_pdf(monkeypatch, tmp_path):
    class Response:
        ok = True
        status_code = 200
        url = "https://example.com/manual.pdf"
        headers = {"content-type": "text/html"}
        content = b"<html>blocked</html>"
        def raise_for_status(self): pass

    monkeypatch.setattr("product_intelligence.pdf_download.requests.get", lambda *a, **k: Response())
    with pytest.raises(ValueError, match="NOT_PDF"):
        download_pdf("https://example.com/manual.pdf", tmp_path, timeout=1)


def test_accepts_pdf_signature(monkeypatch, tmp_path):
    class Response:
        ok = True
        status_code = 200
        url = "https://cdn.example.com/file"
        headers = {"content-type": "application/octet-stream"}
        content = b"%PDF-1.7\nmock"
        def raise_for_status(self): pass

    monkeypatch.setattr("product_intelligence.pdf_download.requests.get", lambda *a, **k: Response())
    result = download_pdf("https://cdn.example.com/file", tmp_path, timeout=1)
    assert result.path.read_bytes().startswith(b"%PDF-")
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `pytest tests/test_pdf_download.py -v`

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement validated download**

Validate with this rule:

```python
ctype = (response.headers.get("content-type") or "").lower()
is_pdf = (
    "application/pdf" in ctype
    or response.content.startswith(b"%PDF-")
    or urlparse(response.url).path.lower().endswith(".pdf") and response.content.startswith(b"%PDF-")
)
if not is_pdf:
    raise ValueError("NOT_PDF")
```

Write bytes atomically, compute SHA256, and return metadata.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_pdf_download.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/pdf_download.py src/product_intelligence/document_ingestion.py tests/test_pdf_download.py
git commit -m "feat: validate PDF downloads before ingestion"
```

---

### Task 7: Ensure OCR and Mistral only run after an accepted PDF exists

**Files:**
- Modify: `src/product_intelligence/document_ingestion.py`
- Modify: `src/product_intelligence/pipeline.py`
- Test: `tests/test_pipeline_document_ingestion.py`

**Interfaces:**
- Consumes: validated `DownloadedPdf` or existing accepted PDF path.
- Guarantees: no OCR/Mistral call occurs for zero-document discovery, HTML responses, or rejected PDF identity.

- [ ] **Step 1: Write failing orchestration test**

```python
def test_no_ocr_or_mistral_when_no_pdf_was_accepted(monkeypatch):
    called = {"ocr": 0, "mistral": 0}
    monkeypatch.setattr(
        "product_intelligence.pipeline.run_ocr",
        lambda *a, **k: called.__setitem__("ocr", called["ocr"] + 1),
        raising=False,
    )
    monkeypatch.setattr(
        "product_intelligence.pipeline.run_mistral",
        lambda *a, **k: called.__setitem__("mistral", called["mistral"] + 1),
        raising=False,
    )

    # invoke the document branch with an empty accepted-document list
    # using the existing pipeline entry point for PDF enrichment
    result = ...
    assert called == {"ocr": 0, "mistral": 0}
```

Before implementation, replace `...` with the actual existing PDF-enrichment entry point found in `pipeline.py`; do not add a duplicate API.

- [ ] **Step 2: Run the focused test and verify RED if current routing permits premature provider calls**

Run: `pytest tests/test_pipeline_document_ingestion.py -v`

Expected: either RED on provider routing or existing PASS; if existing PASS, retain behavior and add an explicit regression assertion around the actual entry point.

- [ ] **Step 3: Add explicit accepted-PDF gate if needed**

Use the existing ingestion result to guard provider execution:

```python
if not accepted_documents:
    return existing_result_without_document_evidence
```

Do not modify OCR/Mistral parsing logic.

- [ ] **Step 4: Run provider and PDF pipeline tests**

Run: `pytest tests/test_pipeline_document_ingestion.py tests/test_provider_ocr_mistral_integration.py tests/test_pdf_evidence_pipeline.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/document_ingestion.py src/product_intelligence/pipeline.py tests/test_pipeline_document_ingestion.py
git commit -m "test: gate OCR and Mistral behind accepted PDFs"
```

---

### Task 8: Surface the real PDF search stages in the desktop log

**Files:**
- Modify: `src/product_intelligence/batch.py`
- Modify: `src/product_intelligence/pdf_desktop.py`
- Test: `tests/test_source_strategy_routing.py`
- Test: `tests/test_pdf_search_trace.py`

**Interfaces:**
- Consumes: `PdfSearchTrace.events` and `summary()`.
- Produces user-visible lines including query, HTTP result count, browser fallback, browser result count, PDF links, download status, and terminal summary.

- [ ] **Step 1: Write a failing formatting test**

```python
from product_intelligence.pdf_search_trace import PdfSearchTrace, format_trace_lines


def test_trace_lines_never_hide_zero_result_stage():
    trace = PdfSearchTrace("JBLQ350WLBLKAM")
    trace.emit("PDF_SEARCH_QUERY", query="JBLQ350WLBLKAM pdf", transport="http")
    trace.emit("PDF_SEARCH_HTTP_RESULT", result_count=0)
    trace.emit("PDF_SEARCH_BROWSER_FALLBACK", query="JBLQ350WLBLKAM pdf")
    trace.emit("PDF_SEARCH_BROWSER_RESULT", result_count=8)
    text = "\n".join(format_trace_lines(trace))
    assert "JBLQ350WLBLKAM pdf" in text
    assert "HTTP" in text and "0" in text
    assert "BROWSER" in text and "8" in text
```

- [ ] **Step 2: Run test and confirm RED**

Run: `pytest tests/test_pdf_search_trace.py::test_trace_lines_never_hide_zero_result_stage -v`

Expected: FAIL because formatter does not exist.

- [ ] **Step 3: Implement formatter and wire it to batch logging**

Use compact lines such as:

```text
  PDF SEARCH query: JBLQ350WLBLKAM pdf
  HTTP SEARCH: 0 resultados
  BROWSER FALLBACK: activado
  BROWSER SEARCH: 8 resultados
  LANDING PAGES: 2 | PDF LINKS: 3
  PDF DOWNLOADS: 2 OK | 1 rechazado
```

If all stages produce zero, end with:

```text
  SIN PDF VALIDADO: queries=7 http_results=0 browser_results=0 landing_pages=0 pdf_links=0
```

Do not collapse this into only `no hubo candidatos`.

- [ ] **Step 4: Run focused UI/routing tests**

Run: `pytest tests/test_pdf_search_trace.py tests/test_source_strategy_routing.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/product_intelligence/pdf_search_trace.py src/product_intelligence/batch.py src/product_intelligence/pdf_desktop.py tests/test_pdf_search_trace.py tests/test_source_strategy_routing.py
git commit -m "feat: expose real PDF search diagnostics"
```

---

### Task 9: Add an integration smoke that proves browser fallback on the three JBL Part Numbers

**Files:**
- Create: `.github/workflows/pdf-search-integration-smoke.yml`
- Create: `tests/integration_pdf_search_smoke.py`
- Test data: `tests/fixtures/jbl_official_regression.json`

**Interfaces:**
- Consumes live network and bundled/installed Playwright Chromium.
- Produces a machine-readable summary artifact; it must not require OCR.space or Mistral API keys.

- [ ] **Step 1: Create integration script**

The script must iterate exactly:

```python
PART_NUMBERS = [
    "JBLQ350WLBLKAM",
    "JBLENDURRUN3BTBAM",
    "JBLT530CBLKAM",
]
```

For each identity, call `discover_product_documents` with a fresh `PdfSearchTrace` and print JSON containing:

```json
{
  "part_number": "JBLQ350WLBLKAM",
  "queries": 7,
  "http_results": 0,
  "browser_results": 8,
  "pdf_candidates": 2,
  "browser_fallback_executed": true
}
```

The smoke should fail only when the architecture itself fails to execute search/fallback or crashes. It must not require every product to have a public PDF forever, because web availability is externally variable.

- [ ] **Step 2: Add workflow**

Use `ubuntu-latest`, install the desktop/test dependencies and `playwright install chromium`, then run:

```bash
python tests/integration_pdf_search_smoke.py
```

Upload the JSON output as an artifact.

- [ ] **Step 3: Run workflow on the feature branch**

Expected: workflow completes and the artifact proves that queries were executed and browser fallback can return results when HTTP search is ineffective.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/pdf-search-integration-smoke.yml tests/integration_pdf_search_smoke.py
git commit -m "test: add live PDF search integration smoke"
```

---

### Task 10: Lock credential persistence across upgrades

**Files:**
- Modify: `tests/test_auto_updater.py`
- Modify: `tests/test_provider_settings.py`
- Modify: `tests/test_provider_settings_desktop.py`

**Interfaces:**
- Verifies existing keyring and `%LOCALAPPDATA%` design; no new credential store.

- [ ] **Step 1: Add regression tests that installation paths exclude settings and keyring data**

Test source contracts for:

```python
assert "LOCALAPPDATA" in provider_settings_source
assert 'SERVICE = "ProductIntelligence"' in key_store_source
assert "settings.json" not in updater_copy_manifest_or_install_source
```

Also retain existing tests that keys are loaded via `load_value` rather than stored in `settings.json`.

- [ ] **Step 2: Run credential/updater tests**

Run: `pytest tests/test_auto_updater.py tests/test_provider_settings.py tests/test_provider_settings_desktop.py -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_auto_updater.py tests/test_provider_settings.py tests/test_provider_settings_desktop.py
git commit -m "test: protect provider credentials across upgrades"
```

---

### Task 11: Full regression and Windows release gate

**Files:**
- Modify version files only after all functional tests are green:
  - `src/product_intelligence/version.py`
  - `pyproject.toml`
  - version contract tests if present

**Interfaces:**
- Final deliverable: next Windows release from `release/windows` only after CI and Windows bundle gates pass.

- [ ] **Step 1: Run the complete test suite**

Run:

```bash
pytest -q
```

Expected: all tests PASS.

- [ ] **Step 2: Run PDF live integration smoke**

Run the new workflow and inspect the JSON artifact. Confirm at least that each of the three JBL Part Numbers shows the actual queries attempted and that browser fallback status is explicit.

- [ ] **Step 3: Run existing smoke workflows**

Do not publish if existing Price Intelligence, Multimedia, desktop shell, or updater smoke fails.

- [ ] **Step 4: Bump the next patch version**

Use the next version after the current `v0.10.17`; at execution time verify `release/windows` latest version before choosing the patch number.

- [ ] **Step 5: Open PR against `release/windows`**

PR body must state:

```text
Solo PDF now performs real Part Number-first PDF discovery with HTTP fast path + Playwright/Chromium browser fallback. HTML pages are discovery bridges only; final evidence remains PDF-only. Adds validated PDF download and stage-by-stage observability. OCR/Mistral semantics unchanged. Credential persistence unchanged and regression-protected. main untouched.
```

- [ ] **Step 6: Merge only after all required checks pass**

- [ ] **Step 7: Follow Release Windows until all steps are SUCCESS**

Required gates:

- version consistency
- full regression tests
- desktop smoke
- bundled Chromium
- clean PyInstaller build
- executable/resource verification
- standalone updater bootstrap
- ZIP + SHA256
- GitHub Release publication

- [ ] **Step 8: User validation on the same three JBL Part Numbers**

Expected log shape:

```text
[1/3] JBLQ350WLBLKAM
  PDF SEARCH query: JBLQ350WLBLKAM pdf
  HTTP SEARCH: ... resultados
  BROWSER FALLBACK: SI/NO
  BROWSER SEARCH: ... resultados
  PDF LINKS: ...
  PDF DOWNLOADS: ...
  PDF VALIDADO: SI/NO
```

The user should no longer receive only `SIN FUENTE VALIDADA: no hubo candidatos` without the preceding stage diagnostics.
