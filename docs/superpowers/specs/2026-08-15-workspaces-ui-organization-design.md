# Workspace and UI Organization Design

## Goal

Organize Multimedia, Price Intelligence, and Trabajos without changing the scraping, PDF, media, price, OCR/Mistral, updater, or identity engines.

## Constraints

- Base branch: `release/windows`; never touch `main`.
- UI/layout changes must remain additive around existing engines.
- Workspace database remains in the existing persistent application location (`%LOCALAPPDATA%\ProductIntelligence\workspaces.db` on Windows).
- User-created work files live outside the installation directory so updater/reinstall operations do not own or replace them.
- Default workspace root on Windows: `Documents\ProductIntelligence\Trabajos`.
- Existing workspaces remain readable even if they were created before physical workspace folders existed.
- Destructive file deletion always requires an explicit confirmation path separate from normal workspace deletion.

## Workspace folders

Each workspace receives a sanitized, collision-safe folder under the root:

```text
Documents\ProductIntelligence\Trabajos\<Trabajo>\
  Excel\
  Scraping\
  PDF\
  multimedia\
  prices\
  Logs\
```

`multimedia` and `prices` intentionally keep the existing engine conventions. The workspace root becomes the active output root when a workspace is opened/created, so existing engines continue creating their current subdirectories without being rewritten.

The workspace folder path is deterministic from workspace id + sanitized display name, avoiding collisions between jobs with equal names. Existing rows need no database migration.

## Trabajos UI

The page keeps create/list/open behavior and adds:

- `Abrir carpeta`
- `Eliminar trabajo` — deletes database record only; files stay on disk.
- `Eliminar trabajo y archivos...` — explicit destructive action with confirmation.
- `Limpiar resultados` — clears generated output subfolders but preserves the workspace row and original Excel path/file.
- `Actualizar lista`

A workspace that is currently running core, multimedia, or prices cannot be deleted or cleaned.

## Multimedia UI

Keep `run_media_product()` unchanged. Reorganize the page into nested tabs:

- `Buscar`: product selector, manual URLs, actions, status, progress.
- `Galería`: existing cards/canvas.
- `Auditoría`: a local event table mirrored from the existing media event stream.

No discovery/download/validation semantics change.

## Price UI

Keep `run_price_product()` unchanged. Reorganize into nested tabs:

- `Buscar`: product selector, actions, compact status and progress.
- `Ofertas`
- `Cobertura`
- `Auditoría`

Existing offer/coverage/audit models and callbacks remain the same.

## Safety and tests

Tests must cover Windows-safe path sanitization, deterministic workspace folder creation, delete-record-only, delete-with-files, clean-results preserving Excel, active-run guards, and UI contracts proving the nested tabs/buttons exist while engine entry points remain unchanged.
