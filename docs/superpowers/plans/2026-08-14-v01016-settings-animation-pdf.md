# v0.10.16 settings, animation and PDF discovery fixes

Base: `release/windows` at v0.10.15. `main` remains untouched.

## Scope

1. Make provider settings save observable and verifiable: inline status, read-back verification, explicit error state.
2. Stop progress GIFs from restarting on every repeated RUNNING event so animations visibly advance.
3. Fix PDF-only discovery so HTML document landing pages are resolved into actual PDF links before PDF ingestion; never send a normal HTML landing page directly to the PDF processor.
4. Preserve identity/evidence gates, OCR.space behavior, Mistral evidence-only semantics, Excel mapping, Price Intelligence, Multimedia and updater.
5. Bump and publish v0.10.16 only after full CI and Windows release gates pass.

## Verification

- Regression tests reproduce all three defects before production changes.
- Full pytest suite passes.
- Existing provider/document/progress contracts remain green.
- Windows release builds ProductIntelligence.exe and ProductIntelligenceUpdater.exe, verifies progress assets and updater bootstrap, then publishes ZIP + SHA256.
