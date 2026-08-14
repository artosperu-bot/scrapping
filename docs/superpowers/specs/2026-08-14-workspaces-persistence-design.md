# ProductIntelligence — Persistent Workspaces & Template Profiles Design

## Goal
Add persistent multi-job workspaces above the existing shared ProductIntelligence engines, preserving v0.10.9 behavior when the feature is unused.

## Constraints
- Base and release line: `release/windows`.
- Baseline: v0.10.9 (`c271af30fa6483f90b1a08ba8cb245ec5b643f31`).
- Historical regression floor: v0.10.4.
- Never modify `main`.
- Preserve scraping, OCR.space, Mistral, PDF evidence, Multimedia, Price Intelligence, canonical/evidence, Configuración, updater, auto-update and current Excel behavior.

## Model
`WORKSPACE -> PRODUCT -> RUN -> STAGE`.

Stages: `IDENTITY`, `EVIDENCE`, `PDFS`, `CANONICAL`, `EXCEL`, `MULTIMEDIA`, `PRICES`.
Statuses: `PENDING`, `RUNNING`, `COMPLETED`, `ERROR`, `PAUSED`.

## Persistence
Use local SQLite via the Python standard library. Every record carries explicit ownership IDs. Stage transitions are transactional. On recovery, interrupted `RUNNING` stages become `PENDING`; `COMPLETED` stages remain completed and are skipped by normal resume.

## Template profiles
Profiles map canonical field names to marketplace Excel columns and optional allowed values/formatters. Profiles adapt output only; they never change extraction, evidence or canonical truth.

## Compatibility
Existing direct workflows remain valid and unchanged. The new subsystem is additive and initially integrates through a new `Trabajos` workspace in the modern desktop shell. It does not replace `batch.py`, `price_workflow.py`, PDF/media/canonical engines or updater code.

## UI
Add a `Trabajos` page that can create/select persistent workspaces, associate an Excel path and template profile, display status, and reopen prior work. The existing pages remain the execution surfaces.

## Resume
A workspace service exposes the next incomplete stage for each product/run. Fine-grained background continuation after UI shutdown is explicitly out of scope; persistence and safe restart come first.

## Tests
Cover persistence across reopen, workspace/product isolation, interrupted-run recovery, completed-stage resume semantics, template profile mapping without input mutation, and desktop navigation registration.
