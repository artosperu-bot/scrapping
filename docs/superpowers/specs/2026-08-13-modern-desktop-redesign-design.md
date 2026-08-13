# Modern Desktop Redesign — Product Intelligence

Date: 2026-08-13
Status: Approved design

## Goal

Replace the current visually incremental Tkinter desktop shell with a genuinely redesigned desktop experience while preserving the existing scraping, Excel, media, price-intelligence, validation, output, and audit behavior.

The redesign must be visible immediately when the packaged Windows executable opens. Success is not “more tabs” or “different labels”; success is a materially different information architecture and visual hierarchy.

## Non-goals

- Do not rewrite the scraping engine.
- Do not rewrite Excel mapping/preflight logic.
- Do not rewrite price intelligence, media discovery/download, identity validation, or persistence/output contracts.
- Do not change result semantics simply to support the UI.
- Do not introduce cloud dependencies or an API key requirement for the desktop shell.

## Architecture

Use a presentation-layer redesign over the current domain/workflow modules. The application entry point must point to the new final desktop shell rather than the current inheritance chain whose visible structure is still based on the original notebook UI.

Existing workflow/service modules remain the source of truth:

- Excel preflight and product identity
- scraping/batch execution
- source discovery and validation
- multimedia workflow
- price intelligence workflow
- output folders and generated Excel/JSON artifacts
- audit/log events

The redesigned UI may reuse existing callbacks and workflow functions, but visual composition belongs to a dedicated final shell so future functional extensions do not force the entire interface back into a notebook hierarchy.

## Visual structure

### 1. Application frame

- Modern desktop frame with a persistent left navigation rail.
- Clear product name/header area and current-workspace title.
- Main content area separated from navigation.
- Consistent spacing, typography, card surfaces, and action hierarchy.
- Status area that makes current activity and errors visible without forcing the user to open logs.

### 2. Navigation

Primary destinations:

1. Inicio / Dashboard
2. Productos
3. Fuentes
4. Atributos
5. Multimedia
6. Precios
7. Ejecutar
8. Auditoría

Navigation changes the main workspace instead of exposing eight numbered notebook tabs as the primary interaction model.

### 3. Dashboard

The initial screen must make the application obviously different from the current build. It should show:

- selected Excel/workbook state;
- number of detected products;
- source readiness;
- media/price readiness or recent status;
- output folder;
- primary actions to select/analyze an Excel and continue the workflow.

### 4. Products workspace

- Modern table/list treatment for detected products.
- Clear identity type, identifier, brand, model/name, URL count, and state.
- Edit action remains available.
- Selection should drive contextual actions used by Sources, Media, and Prices.

### 5. Sources workspace

- Product selector/context on the left or top.
- Manual URLs in a dedicated panel.
- Candidate-source plan in a readable table/card region.
- Preserve current priority rules and identity validation.

### 6. Attributes workspace

- Keep the existing Excel attribute contract and values.
- Improve readability with a clear title, explanation, filters/summary where practical, and a spacious table.
- Seller/STECH-only fields remain protected and may remain empty.

### 7. Multimedia workspace

- Preserve current media discovery, gallery, progress, downloaded/external counts, and error reporting.
- Keep the wolf/progress concept only if it fits the redesigned layout; it must not dominate or make the UI look experimental.
- Progress must remain truthful to workflow events.

### 8. Price workspace

- Preserve current price workflow and validated offers.
- Show selected product, actions, progress, result summary, and offer table in a modern workspace.
- Preserve seller/channel separation, currency formatting, stock/confidence, and double-click/open-link behavior.

### 9. Execute workspace

- Output folder and overwrite/reinvestigation settings.
- Prominent primary CTA for scraping + Excel generation.
- Pre-run summary before execution.
- Do not alter protection of seller/STECH fields.

### 10. Audit workspace

- Live process output with readable hierarchy.
- Clear/reset and open-output-folder actions.
- Errors should also surface in the global status area.

## Behavior preservation

The redesign must preserve at minimum:

- Excel selection and automatic analysis;
- product identity detection/editing;
- manual URL storage and preview;
- source discovery priorities;
- attribute inspection;
- scraping batch execution;
- generated Excel/output behavior;
- JSON repair/reprocess path;
- media processing and progress;
- price processing and progress;
- opening result URLs;
- logs/audit events;
- frozen Playwright/Chromium behavior inside the Windows bundle.

## Error handling

- Long-running work remains off the Tk main thread.
- Buttons/actions are disabled while their workflow is active where duplicate starts would be unsafe.
- Fatal worker errors are surfaced both in the current workspace and audit log.
- UI errors must not silently mutate product identity, results, or output files.
- Existing workflow exceptions remain inspectable in audit output.

## Testing

### Automated regression

The existing test suite remains mandatory. New tests should cover the final shell at the contract level without requiring pixel-perfect screenshot testing:

- application final entry point resolves to the redesigned shell;
- all primary destinations exist;
- preserved callbacks/actions are reachable;
- analyzing a workbook populates shared product state used by Products/Media/Prices;
- price/media workflow state updates still map to progress UI;
- output and audit controls remain wired.

### Build gate

GitHub Actions `Build Windows EXE` must pass all of:

1. install desktop dependencies;
2. regression tests;
3. bundled Chromium install;
4. PyInstaller build;
5. explicit verification that `dist\\ProductIntelligence\\ProductIntelligence.exe` exists;
6. upload fresh `ProductIntelligence-Windows` artifact.

## Acceptance criteria

The redesign is complete only when all conditions below are true:

- Opening the new executable is visually and structurally distinguishable from the previous notebook-based build without needing to navigate to a newly added tab.
- Persistent navigation replaces the numbered notebook tabs as the primary application shell.
- Dashboard is the initial user-facing workspace.
- Products, Sources, Attributes, Multimedia, Prices, Execute, and Audit remain usable.
- Existing functional tests pass.
- A fresh Windows build generated from the redesign commit completes successfully.
- The workflow verifies `ProductIntelligence.exe` and uploads a new artifact tied to that commit.

## Implementation boundary

Prefer a dedicated modern presentation shell and reusable UI helpers/styles rather than modifying business modules. Avoid a technology migration that would force rewriting the working engine. The implementation may remain in the current Python desktop stack provided the resulting interface is materially redesigned and the packaged executable remains self-contained.
