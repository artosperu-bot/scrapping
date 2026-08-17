# ProductIntelligence v0.10.25 Live UI Observability Design

## Goal
Make every long-running desktop workflow visibly observable while it runs, without changing the validated business/search/identity/evidence rules.

## Architecture
Introduce one small reusable live-event contract for UI-facing state. Workers continue to run outside Tk's main thread and emit plain dictionaries/events. Tk consumes those events through queues and `after()` callbacks only. Each event is scoped by module, workspace, product, and run id so results cannot leak across products or workspaces.

The existing extension chain is preserved. No rewrite of Tkinter shell, scraping engines, PDF approval semantics, OCR/Mistral semantics, price validation, media quality gates, or updater behavior.

## Event contract
Minimum fields when known: `type`, `module`, `run_id`, `product_index`, `product_label`, `stage`, `action`, `source`, `status`, `found`, `accepted`, `rejected`, `error`, `elapsed_seconds`, and module payload (`offer`, `candidate`, `media`, `download`). Unknown values are omitted rather than invented.

## UI state model
A per-run state store retains current stage, counters, accepted/rejected items, errors, and completion state. Views render from this store, so changing tabs does not erase valid results. New runs explicitly reset only the corresponding module/product state.

## Module behavior
### Price
Existing incremental `offer` events remain authoritative. Add truthful counters/stages, dedupe by stable offer identity, visible source processing, explicit `0 ofertas válidas`, and error recovery. A price row must be inserted before the product `done` event whenever an offer is accepted.

### PDF Review
Discovery emits candidate-level events during search/validation. Validated candidates are added to the review list immediately. Rejected/duplicate/error events remain visible in audit. Discovery never activates OCR or Mistral and no PDF becomes evidence before explicit review confirmation.

### Multimedia
Existing media events feed live counters and gallery updates. Valid downloaded image/video cards appear immediately. Rejected media stays observable in audit.

### Social Video
`yt-dlp` progress data is surfaced only when actually reported: downloaded bytes, total bytes, speed, ETA, post-processing, verification, completed path/size. Completion adds the MP4 to gallery immediately.

### Scraping Excel
Expose product/phase progress using real stages only: IDENTITY, SEARCH, VALIDATE, EXTRACT, PDF, OCR, MISTRAL, SEMANTIC RESOLUTION, WRITE EXCEL. OCR/Mistral stages appear only when invoked. Product results/counters update before the whole batch finishes.

### Audit / cross-view preservation
Important engine events are appended live and retained for the current run. Switching views must not clear accepted prices, PDF candidates, media cards, or current-run audit events.

## Threading and errors
Heavy work remains off the Tk main thread. Workers never mutate Tk widgets directly. UI handlers catch exceptions so one bad event cannot stop future queue draining. A worker failure emits ERROR, restores controls, and permits the next execution.

## Gates
UI-1 Price: RUNNING visible, real stages, first accepted price visible before product completion, UI responsive, final state retained.
UI-2 PDF: live search/candidates/validation, review before use, no unapproved evidence.
UI-3 Media: live progress, incremental cards, responsive gallery.
UI-4 Social video: truthful download/post-process progress, real MP4, immediate card.
UI-5 Error recovery: RUNNING -> ERROR -> controls restored -> next run allowed.

## Release rule
Do not bump or publish v0.10.25 until critical live-UI gates and existing regression/Windows packaging checks are green.
