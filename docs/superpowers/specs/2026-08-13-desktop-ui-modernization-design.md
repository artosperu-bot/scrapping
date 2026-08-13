# Desktop UI Modernization Design

Date: 2026-08-13
Branch: `ui-modernization-v1`
Base: `price-intelligence-multilayer`

## Goal

Modernize the Windows desktop UI/UX without changing the existing scraping, multimedia, price intelligence, Excel, validation, persistence, or concurrency logic. The executable must remain functionally equivalent from the engine perspective while becoming clearer, more professional, and easier to follow during multiple simultaneous long-running processes.

## Visual direction

Style A: light, business-oriented, modern.

- Light neutral application background.
- White content cards with subtle borders and restrained spacing.
- Dark blue accent for primary actions and selected navigation.
- Segoe UI typography.
- Clear hierarchy: page title, context, primary action, progress, results.
- Consistent component spacing and alignment across all modules.
- Tom & Jerry GIFs are functional process-state illustrations only, not general decoration.

## Navigation and information architecture

Keep all existing capabilities, but organize the application visually into three groups:

### Preparation
- 1. Excel
- 2. Products
- 3. Sources
- 4. Attributes

### Operations
- 5. Execute
- 7. Multimedia
- 8. Prices

### System / follow-up
- 6. Logs / Audit

The internal module numbering and existing commands remain compatible. Logs should visually behave as a secondary monitoring area while Multimedia and Prices remain first-class operational modules.

## Universal process status component

Create a reusable process-status card for every long-running operation.

Each card shows:
- process type;
- process/session id;
- selected product or batch label;
- start time;
- current status text;
- product progress;
- overall progress when applicable;
- summary counters;
- state illustration.

### GIF state mapping

Use the two user-provided GIFs as packaged local assets in the executable:

1. `process_running.gif` — Tom chasing Jerry — displayed while a process is active: searching, validating, scraping, downloading, saving, or otherwise processing.
2. `process_complete.gif` — Tom serving the completed hot dog — displayed when the process reaches 100% successfully.

The GIFs must be resized to fit a compact card area while preserving aspect ratio and animation. They must not be stretched. They must be bundled into the PyInstaller executable and require no network access.

Error/cancelled states do not use the completion GIF. They use a normal text/status treatment and existing error information.

## Concurrent processes

The UI must support simultaneous independent operations without introducing a new global lock.

Existing engine isolation remains authoritative:
- multimedia continues to own `_media_running`;
- price intelligence continues to own `_price_running`;
- Excel/base execution keeps its existing lifecycle;
- UI changes must not serialize unrelated modules.

Each active process receives its own process/session state object and its own status card. A user may run Multimedia and Prices concurrently. Their progress events must remain separated while the combined log view may display both.

No background worker may read or write Tkinter widgets directly. Workers continue to publish plain Python events to queues, and the UI thread renders those events.

## Logs / Audit redesign

Replace the single undifferentiated log experience with execution sessions while preserving the existing underlying log stream.

Required UI:
- `Todos` tab: combined chronological stream from all processes;
- one tab per execution/session, such as `Precios #005`, `Multimedia #006`, `Excel #007`;
- each execution tab shows process name, product/batch, start time, state, percentage, and only that execution's messages;
- completed execution tabs remain available during the application session;
- errors remain visible in the matching execution and in `Todos`.

The implementation should add routing metadata to UI log events, not alter scraper business logic.

## Multimedia UI

Preserve existing actions and gallery behavior.

Reorganize into:
1. product selector and optional URLs;
2. primary action area;
3. universal process status card;
4. image/video result gallery.

Remove the current custom-drawn wolf animation and all wolf-specific status text. Replace it with the universal GIF process-state component.

## Price Intelligence UI

Preserve current `run_price_product` behavior and result fields.

Reorganize into:
1. product selector and actions;
2. summary metric cards: best verified price, offer count, target-channel count, individual-store count when available;
3. universal process status card;
4. validated-offer table.

Keep columns for product, channel, seller, price, list price, stock, confidence, and URL. Improve alignment and visual hierarchy but do not change the meaning of the values.

## Execute / Excel process UI

Long-running base/Excel execution also uses the universal status component. The current scraping and Excel generation pipeline remains unchanged. The UI should show stage, current product, overall progress when available, and the running/completed GIF state.

## Theme implementation boundaries

Introduce reusable UI-only helpers/components where useful, for example:
- theme/style configuration;
- process session model;
- process status card;
- GIF animation widget;
- session log notebook/router.

Do not move extraction, identity, marketplace, price, media, Excel, or browser logic into UI modules.

Avoid unrelated refactors.

## Asset packaging

Copy the two provided GIF files into the repository under the desktop asset directory using stable names:
- `src/product_intelligence/assets/process_running.gif`
- `src/product_intelligence/assets/process_complete.gif`

`ProductIntelligence.spec` already packages `src/product_intelligence/assets`; preserve that mechanism and verify the final Windows build resolves assets both from source and from `sys._MEIPASS`.

## Failure handling

- Missing/corrupt GIF: UI falls back to a static textual process state; the operation itself must continue.
- UI rendering error: do not terminate the scraping worker.
- Worker error: route to matching session log and set card state to error.
- Concurrent session events: route by stable session id so one operation cannot overwrite another's visual state.

## Testing and acceptance criteria

### Regression
All existing tests must remain green before merge.

### New unit/UI-logic tests
Cover at minimum:
- process session creation and independent ids;
- routing events to the correct session;
- `Todos` receives every routed log event;
- two concurrent process sessions do not overwrite each other;
- running -> complete state switch at 100%;
- failure state does not show completion state;
- missing GIF produces fallback instead of exception;
- asset path resolves in source mode and frozen/PyInstaller mode;
- price and media running guards remain independent.

### Manual executable verification
Build through `CONSTRUIR_EXE_WINDOWS.bat` and verify:
1. application launches;
2. existing Excel analysis works;
3. Multimedia starts and shows running GIF;
4. Prices starts while Multimedia is still running;
5. both have distinct process cards and log sessions;
6. `Todos` shows combined logs;
7. each process-specific tab shows only its own events;
8. successful completion switches only that process to the completion GIF;
9. results remain identical in meaning to the pre-UI version;
10. no new engine/business-logic regressions.

## Non-goals

- No changes to product identity rules.
- No changes to price discovery/extraction logic.
- No changes to media discovery/download logic.
- No changes to Excel mapping/business rules.
- No changes to external APIs or scraping strategy.
- No new global process lock.
- No redesign of persistence contracts.

## Definition of done

The UI looks consistent, ordered, and business-oriented; long-running operations share one coherent status language; Tom & Jerry GIFs communicate active/completed states; simultaneous processes remain independent; logs are separated by execution; the executable builds successfully; and all pre-existing functional logic remains unchanged and regression-tested.
