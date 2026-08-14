# Source Strategy + Provider Probes — Design

## Goal

Allow each Scraping Excel execution to choose which evidence routes are active (Web, PDF, OCR.space, Mistral) and turn the existing disabled provider-test buttons into real connection probes, without duplicating engines or weakening evidence/canonical safeguards.

## Scope

Target branch: `release/windows` via feature branch `feat/v0.10.14-source-strategy-provider-probes`.

Version target: `v0.10.14`.

`main` remains untouched.

The controls are **per execution only**. They are not persisted as the user's default source strategy. Existing provider credentials/settings remain persistent exactly as today.

## Execution strategy UI

Scraping Excel gets a `Fuentes de esta ejecución` control block with four booleans:

- `Web`: enables normal HTML/web discovery and targeted web follow-up.
- `PDF`: enables PDF links discovered from pages plus direct technical-document discovery.
- `OCR.space`: permits remote OCR fallback for PDF pages that do not contain usable native text.
- `Mistral`: permits the existing guarded Mistral narration/interpretation path.

Quick presets:

- `Automático`: Web ON, PDF ON, OCR ON when configured, Mistral ON when configured.
- `Solo Web`: Web ON, PDF/OCR OFF; Mistral remains available only over evidence already gathered by the run.
- `Solo PDF`: Web OFF, PDF ON, OCR ON; document discovery may still use the project's existing free search discovery to locate PDF URLs, but HTML pages must not be ingested as evidence.
- `Web + PDF`: Web ON, PDF ON; OCR/Mistral follow their checkboxes.

At least one evidence acquisition route (`Web` or `PDF`) must be enabled before execution.

OCR requires PDF. Turning PDF off forces OCR off for that run and the UI reflects this dependency.

## Pipeline contract

Introduce a focused per-run strategy object/dict passed from the desktop snapshot into `run_batch()` / `scrape_item()`.

The strategy changes routing only; it does not change identity validation, source validation, evidence normalization, conflict resolution, canonical facts, Excel mapping, Multimedia, Price Intelligence, or the updater.

### Web OFF

- Do not call generic HTML `search_web()` for normal page candidates.
- Do not run `search_web_for_fields()` targeted HTML follow-up.
- Manual URLs that are non-PDF are skipped for evidence ingestion.
- If PDF is ON, direct PDF discovery remains allowed so `Solo PDF` can actually locate documents.

### PDF OFF

- Pass `include_pdfs=False` into page processing.
- Do not call `discover_product_documents()`.
- PDF evidence scope is disabled for that execution.
- OCR is forced OFF.

### OCR OFF

`provider_run_scope` receives `ocr_space_enabled=False`, so PDF native text extraction remains available but OCR.space is not called. Existing local OCR fallback behavior is not expanded by this feature.

### Mistral OFF

`provider_run_scope` receives `mistral_enabled=False`; existing deterministic fallback narration remains in force.

## Observability

Each execution snapshot records:

- `source_web_enabled`
- `source_pdf_enabled`
- `ocr_space_enabled`
- `mistral_enabled`
- `mistral_model`
- `request_timeout`

The audit start entry explicitly records the active route set.

Existing provider/PDF events remain the source of truth for whether a provider was actually used. The UI/audit must distinguish configured/enabled from executed.

## Provider connection probes

The disabled `Probar conexión · pendiente` button becomes `Probar conexión` for OCR.space and Mistral.

The probe runs on a background thread and never blocks Tk.

### OCR.space

Use the stored credential and the existing `OCRSpaceClient`. Send a tiny generated PNG containing simple text (`STECH OCR TEST`) to the real OCR endpoint. Success requires a non-empty parsed response. The key is never logged or copied into settings.

States:

- `PROBANDO…`
- `CONECTADO`
- `RECHAZADO` for authentication/HTTP rejection or empty/error provider response
- `ERROR DE RED` for transport failures/timeouts
- `SIN CONFIGURAR` when no stored key exists

### Mistral

Use the stored credential and the existing `MistralClient`. Send a minimal deterministic payload asking for the exact token `STECH_OK` with the configured model. Success requires a non-empty response and no HTTP/authentication exception. The probe is only a credential/connectivity check; it does not alter product data.

States match OCR.space.

## Safety

- API keys stay in the secure key store and are never placed in execution snapshots, logs, audit rows, JSON outputs, Excel, or exception messages shown to the user.
- Provider probes do not write business data.
- No source route may bypass product identity validation.
- `Solo PDF` still validates every PDF identity before accepting evidence.
- Mistral never receives raw rejected evidence; existing canonical-safe narration safeguards remain unchanged.

## Testing

Add regression tests for:

1. source strategy defaults and dependency rules;
2. Web OFF prevents normal web candidate ingestion and targeted web follow-up;
3. PDF OFF prevents direct document discovery and disables PDF scope;
4. Solo PDF can use direct PDF candidates without ingesting HTML pages;
5. execution snapshot contains the selected route flags;
6. provider buttons are enabled and call asynchronous probe handlers;
7. OCR probe success/rejection/no-key behavior with fake transport;
8. Mistral probe success/rejection/no-key behavior with fake transport;
9. no API key appears in returned probe result/audit-safe data;
10. full existing regression suite remains green.

## Release gate

Before merge to `release/windows`:

- Linux CI full regression: PASS.
- Windows release workflow after merge: regression PASS, desktop smoke PASS, PyInstaller PASS, both executables present, standalone updater smoke PASS, ZIP/SHA256 PASS, GitHub release `v0.10.14` published.
