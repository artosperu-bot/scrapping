# Price Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a general automatic `8. Precios y competencia` desktop workflow that discovers and validates public offers by Part Number/model, separates channel from seller, and stores price history without changing Excel or multimedia engines.

**Architecture:** Keep pricing isolated behind normalized offer models and adapters. Try structured platform routes first (MercadoLibre public search and VTEX when a candidate domain actually exposes VTEX), then generic web discovery + structured page extraction, with identity validation before an offer can become competitive. UI subclasses the current multimedia-progress desktop and uses its own worker queue.

**Tech Stack:** Python 3.12, requests, BeautifulSoup/lxml, Pydantic/dataclasses-compatible plain models, Tkinter/ttk, existing `ProductIdentity`, `search_web`, `fetch_page`, Playwright fallback.

## Global Constraints

- Part Number/MPN is the primary identity key; model/brand are fallbacks.
- Channel and seller are separate fields.
- No mandatory manual URLs in v1.
- Structured API/JSON/JSON-LD first; HTML/Playwright fallback.
- Do not invent seller legal name, RUC, stock, or price.
- Do not call `run_batch` or `run_media_product` from pricing.
- Color is not a hard conflict when model identity is otherwise exact; capacity/generation/connectivity conflicts are hard conflicts.
- Persist `latest.json`, append-only `history.jsonl`, and seller cache under `price_intelligence/`.
- UI network work stays off the Tk thread.

---

### Task 1: Normalized offers and identity scoring

**Files:** Create `src/product_intelligence/price_models.py`, `src/product_intelligence/price_identity.py`; Test `tests/test_price_identity.py`.

**Interfaces:** `PriceOffer`, `score_offer_identity(identity, evidence) -> tuple[float, str, list[str]]`, `dedupe_offers(list[PriceOffer])`.

- [ ] Write failing tests for exact MPN, exact GTIN, brand+model fallback, variant conflict, and dedupe.
- [ ] Run targeted tests and confirm RED.
- [ ] Implement minimal normalized model + scoring/dedupe.
- [ ] Run targeted tests and confirm GREEN.

### Task 2: Structured adapters

**Files:** Create `src/product_intelligence/price_adapters.py`; Test `tests/test_price_adapters.py`.

**Interfaces:** `parse_mercadolibre_payload(payload, identity)`, `parse_vtex_payload(payload, identity, channel, source_url)`.

- [ ] Write fixtures in tests for MercadoLibre and VTEX with multiple sellers.
- [ ] Confirm RED.
- [ ] Parse price/list price/seller/stock/url without assuming seller fields always exist.
- [ ] Confirm GREEN.

### Task 3: Generic page extraction and discovery

**Files:** Create `src/product_intelligence/price_discovery.py`; Test `tests/test_price_discovery.py`.

**Interfaces:** `extract_page_offers(html, url, identity, channel=None)`, `discover_price_sources(identity, limit=12)`.

- [ ] Test JSON-LD Offer/AggregateOffer, visible price fallback, seller extraction, and rejection on identity mismatch.
- [ ] Confirm RED.
- [ ] Reuse `search_web` and extract structured page offers first.
- [ ] Confirm GREEN.

### Task 4: History persistence

**Files:** Create `src/product_intelligence/price_history.py`; Test `tests/test_price_history.py`.

**Interfaces:** `save_price_run(output_root, offers)`, `load_latest(output_root)`.

- [ ] Test append-only JSONL, latest consolidation, seller cache.
- [ ] Confirm RED.
- [ ] Implement atomic latest write and JSONL append.
- [ ] Confirm GREEN.

### Task 5: Orchestrated workflow

**Files:** Create `src/product_intelligence/price_workflow.py`; Test `tests/test_price_workflow.py`.

**Interfaces:** `run_price_product(identity, output_root, on_event=None, max_sources=12) -> list[PriceOffer]`.

- [ ] Test adapter failure isolation, generic fallback, confidence filtering, event emission, and isolation from Excel/media workflows.
- [ ] Confirm RED.
- [ ] Implement known-source attempts + discovery + page extraction + dedupe + history.
- [ ] Confirm GREEN.

### Task 6: Desktop tab 8

**Files:** Create `src/product_intelligence/price_desktop.py`; Modify `run_desktop.py`; Test `tests/test_price_desktop.py` and update entrypoint regression.

**Interfaces:** `class App(MediaProgressApp)`, `main()`.

- [ ] Test tab title, buttons, Treeview columns, queue/after usage, URL double-click, and independent price workflow.
- [ ] Confirm RED.
- [ ] Add selected/all processing, table, summary, progress bars, worker queue, and browser opening.
- [ ] Point EXE entrypoint to `price_desktop.main` while preserving inheritance of tabs 1–7.
- [ ] Confirm GREEN.

### Task 7: Verification and integration

- [ ] Run full `python -m pytest -q` in GitHub Actions.
- [ ] Fix only evidenced failures and rerun until green.
- [ ] Open PR, verify mergeable and CI success.
- [ ] Merge to `main` after green because the user explicitly approved implementation/integration.
- [ ] Verify post-merge Windows build workflow status; report artifact/build truthfully.
