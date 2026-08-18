# ProductIntelligence Recovery Updater Design

## Goal
Provide a one-time Windows recovery executable for users still on v0.10.4, whose bundled updater cannot bootstrap because it was packaged as a PyInstaller onedir executable and fails when copied alone to `%TEMP%`.

## Scope
The recovery utility is separate from the main application and does not change scraping, OCR.space, Mistral, PDF evidence, Multimedia, Price Intelligence, Configuration, API keys, or business logic.

## Behavior
`ProductIntelligenceRecoveryUpdater.exe` is a standalone PyInstaller onefile executable built on `windows-latest` in GitHub Actions. It discovers the existing ProductIntelligence installation by checking its own directory first, then the current working directory, and finally a currently running `ProductIntelligence.exe` process. It queries the repository `/releases/latest`, downloads the official `ProductIntelligence-Windows.zip` and `ProductIntelligence-Windows.sha256`, verifies SHA256 before extraction, validates the expected archive root, waits for the running application to close when necessary, overlays the official bundle into the existing installation, and restarts `ProductIntelligence.exe`.

If automatic discovery fails, it does not guess or scan arbitrary disks; it shows a clear message asking the user to place the recovery executable next to the existing `ProductIntelligence.exe` and run it again.

## Safety
The ZIP extraction rejects path traversal and unexpected roots. No update is applied unless SHA256 matches. The target must already contain `ProductIntelligence.exe`. Existing user configuration is preserved because the recovery copies the release bundle over the installation rather than deleting the installation directory first.

## Build and verification
A dedicated GitHub Actions workflow builds only the recovery executable on Windows and uploads it as an Actions artifact. Tests cover target discovery, release asset selection, checksum validation, archive validation, and build contract. The Windows workflow also executes the built EXE with `--self-test` from an isolated temporary directory so the artifact is proven standalone before upload.
