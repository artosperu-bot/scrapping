# Product Intelligence — Process Isolation and Audit UI Design

Date: 2026-08-13
Baseline: `540b1946465dc7e23db73f801791d3177c09392e`

## Goal

Reorganize the desktop application so its major functions are easy to understand and can be executed independently without one run contaminating another. The design must remain generic for arbitrary product categories and must not hardcode behavior around smoke-test SKUs, brands, or models.

## User-facing navigation

The modern shell is simplified around the real functional boundaries:

1. **Inicio** — status and entry points.
2. **Scraping Excel** — all preparation and execution needed to analyze a workbook and generate the enriched Excel. Products, identity, sources, attributes and execution belong inside this area.
3. **Multimedia** — independent photos/videos workflow using validated product identity.
4. **Precios** — independent price/seller/stock intelligence workflow using validated product identity.
5. **Auditoría** — transversal view of all runs and their events.

Products, Sources and Attributes remain available as working views inside Scraping Excel rather than appearing as peer processes beside Multimedia and Precios.

## Process boundaries

There are three executable process types:

- `EXCEL`: analyze/scrape/resolve/write the technical workbook.
- `MEDIA`: discover, validate and download photos/videos.
- `PRICE`: discover and validate offers, channels, sellers and stock.

A process may use the same validated product identity as another process, but it must not mutate another process's execution state.

### Rules

- Excel scraping never automatically triggers Multimedia or Precios.
- Multimedia never changes Excel execution inputs or price results.
- Precios never changes Excel execution inputs or multimedia results.
- Navigation between views must not cancel or reconfigure running jobs.
- Starting another function must not overwrite the inputs of an already-running job.
- A module can prevent a second run of the *same module* if needed, but it must not block unrelated modules.

## Immutable execution snapshots

At the moment the user starts a job, the UI creates a plain-Python execution snapshot containing everything the worker needs.

Example fields:

- `run_id`
- `process_type`
- `started_at`
- workbook path when relevant
- output root
- selected product indexes
- canonical identities / Part Numbers / GTIN / model / product name
- manual source URLs relevant to that module
- module options

Workers receive only the snapshot. They must not read mutable Tkinter variables or live UI collections after the thread starts.

This specifically removes the current risk where the Excel worker reads `self.excel`, `self.out` or `self.overwrite` after execution has begun while other views remain usable.

## Concurrency model

Keep the current desktop application and background-thread model; do not introduce multi-process complexity unless testing proves threads cannot provide safe isolation.

Each module owns:

- its own running flag;
- its own event queue;
- its own progress state;
- its own controls;
- its own execution snapshot.

The shared UI owns only a small transversal audit/event sink.

Expected behavior:

- EXCEL can run while MEDIA runs.
- EXCEL can run while PRICE runs.
- MEDIA can run while PRICE runs.
- The three may run simultaneously when external resources permit.
- One run's failure does not set another run to failed.

## Structured audit/event model

Replace the audit experience based only on a shared text box with structured events while preserving a raw technical log for diagnostics.

Canonical event fields:

- `timestamp`
- `run_id`
- `process_type` (`EXCEL`, `MEDIA`, `PRICE`)
- `product_id` / best canonical identifier when available
- `stage`
- `source`
- `url`
- `status`
- `detail`
- optional `result`

Primary statuses:

- `STARTED`
- `FOUND`
- `ACCEPTED`
- `REJECTED`
- `PROGRESS`
- `ERROR`
- `DONE`

Existing free-form `emit()` messages may continue to feed the raw log, but new module events should also be normalized into the structured audit sink.

## Audit UI

Auditoría becomes a real table, not merely the legacy Text widget behind a modern navigation label.

Columns:

- Hora
- Ejecución
- Proceso
- Producto
- Etapa
- Fuente
- Estado
- Detalle

Filters:

- Todos
- Scraping Excel
- Multimedia
- Precios
- Errores
- Rechazados

Additional search/filter by run ID or product identifier is desirable if it can be added without complicating the initial implementation.

Selecting an event should expose technical detail such as URL and raw message. The raw log remains available as a secondary diagnostic panel or detail view.

## Scraping Excel workspace

Scraping Excel groups the existing Excel-oriented steps in a coherent order:

1. Select/analyze workbook.
2. Review detected products and canonical identity.
3. Review manual/discovered sources.
4. Review attributes requested by the template.
5. Execute scraping and generate Excel.
6. Inspect output and related audit events.

The underlying extraction, resolution, identity and Excel-writing engines remain preserved unless a change is required specifically for execution isolation.

## Multimedia workspace

Preserve the current independent workflow and progress UI. Continue using request/HTML-first extraction with browser fallback and exact-product validation. The key architectural change is that each media run uses a frozen identity/output/manual-URL snapshot and writes only its own events/results.

## Price workspace

Preserve the current independent price intelligence engine and its validated-offer table. Each price run uses a frozen identity/output snapshot and writes only price-related events/results.

## General-product requirement

All UI labels, execution logic, tests and event handling must work with generic product identities. No branch may depend on JBL, HyperX, Ulefone, Quantum, Tune, Endurance or any other example product being present.

Tests should use multiple categories/identity shapes where reasonable, for example:

- MPN-based product;
- GTIN/EAN-based product;
- model/name fallback product.

Smoke products may remain fixtures, but they cannot define product-specific runtime behavior.

## Error handling

- Module errors are emitted with the correct `run_id` and `process_type`.
- A fatal error restores only the controls of the failing module.
- Another active module continues running.
- UI-thread interaction remains restricted to queue draining / `after()` callbacks.
- No worker directly manipulates Tk widgets.

## Compatibility and preservation

Do not rewrite working extraction engines as part of this UI/isolation task.

Preserve:

- Excel-first contract;
- canonical identity protections;
- seller SKU derived from validated Part Number/MPN at Excel output;
- exact-product protection;
- current media extraction rules;
- current price validation rules;
- modern desktop styling;
- existing output directory contracts unless an isolation bug requires a narrowly scoped adjustment.

## Testing and release gates

Minimum regression coverage must prove:

1. Existing Excel analysis still works.
2. Existing Excel scrape/generate flow still works.
3. Multimedia selected/all flows still work.
4. Price selected/all flows still work.
5. Starting MEDIA does not alter an active EXCEL snapshot.
6. Starting PRICE does not alter an active EXCEL snapshot.
7. Starting EXCEL does not alter an active MEDIA/PRICE snapshot.
8. Events from concurrent runs preserve their own `run_id` and process type.
9. Audit filters show only the intended process/status.
10. General-product tests do not rely on one brand/model.

Windows release is closed only after the existing gates pass:

- regression = PASS
- modern desktop smoke = PASS
- Chromium = PASS
- PyInstaller = PASS
- Verify executable exists = PASS
- artifact upload = PASS

## Non-goals

- Do not replace Tkinter.
- Do not redesign scraping algorithms unrelated to isolation.
- Do not introduce a database only for logs.
- Do not introduce multi-process workers unless thread isolation proves insufficient.
- Do not couple Media or Price execution to Excel generation.

## Success criteria

A user can clearly see where to run each function, can start the desired process without confusing it with another, and can inspect a single ordered audit view that identifies exactly which execution produced each event. Concurrent functions do not overwrite one another's inputs, status, progress or completion state.