# ProductIntelligence v0.10.36

Release candidate promoted from the certified v0.10.36 head.

## User-visible changes

- Price Intelligence: optional manual Part Number / MPN input that reuses the existing price workflow unchanged.
- Video by URL: resilient YouTube support with bundled EJS/Deno runtime and webpage embedded-video fallback.

## Update compatibility

- Upgrade path: v0.10.35 -> v0.10.36 through the existing in-app updater.
- Release assets remain `ProductIntelligence-Windows.zip` and `ProductIntelligence-Windows.sha256`.
- Existing SHA256 verification, safe extraction, external updater replacement and restart flow are preserved.

## Certified pre-release gates

- Full CI: PASS.
- Social Video Download Smoke: PASS.
- Price Intelligence live smoke: PASS after live-source retry.
- Windows EXE build: PASS.
- Packaged SMART E2E: PASS.
- Standalone updater bootstrap: PASS.
