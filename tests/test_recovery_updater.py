from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from product_intelligence import recovery_updater


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return data.getvalue()


def test_discover_target_prefers_recovery_exe_sibling(tmp_path):
    recovery = tmp_path / "ProductIntelligenceRecoveryUpdater.exe"
    recovery.write_bytes(b"recovery")
    app = tmp_path / "ProductIntelligence.exe"
    app.write_bytes(b"app")
    target, pid = recovery_updater.discover_target_dir(recovery, tmp_path / "other")
    assert target == tmp_path
    assert pid is None


def test_discover_target_uses_cwd_when_sibling_missing(tmp_path):
    recovery_dir = tmp_path / "downloads"
    recovery_dir.mkdir()
    recovery = recovery_dir / "ProductIntelligenceRecoveryUpdater.exe"
    recovery.write_bytes(b"recovery")
    install = tmp_path / "install"
    install.mkdir()
    (install / "ProductIntelligence.exe").write_bytes(b"app")
    target, pid = recovery_updater.discover_target_dir(recovery, install)
    assert target == install
    assert pid is None


def test_parse_sha256_accepts_standard_sha_file():
    digest = "a" * 64
    assert recovery_updater.parse_sha256(f"{digest}  ProductIntelligence-Windows.zip\n") == digest


def test_parse_sha256_rejects_invalid_text():
    with pytest.raises(ValueError, match="SHA256"):
        recovery_updater.parse_sha256("not-a-checksum")


def test_select_release_assets_requires_zip_and_sha():
    payload = {
        "tag_name": "v0.10.6",
        "assets": [
            {"name": "ProductIntelligence-Windows.zip", "browser_download_url": "https://example.invalid/app.zip"},
            {"name": "ProductIntelligence-Windows.sha256", "browser_download_url": "https://example.invalid/app.sha256"},
        ],
    }
    assert recovery_updater.select_release_assets(payload) == (
        "0.10.6",
        "https://example.invalid/app.zip",
        "https://example.invalid/app.sha256",
    )


def test_select_release_assets_fails_closed_when_asset_missing():
    payload = {"tag_name": "v0.10.6", "assets": []}
    with pytest.raises(ValueError, match="release assets"):
        recovery_updater.select_release_assets(payload)


def test_verify_download_rejects_digest_mismatch(tmp_path):
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(b"payload")
    with pytest.raises(ValueError, match="SHA256"):
        recovery_updater.verify_sha256(archive, "0" * 64)


def test_verify_download_accepts_matching_digest(tmp_path):
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    recovery_updater.verify_sha256(archive, digest)


def test_safe_extract_bundle_requires_expected_root(tmp_path):
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(_zip_bytes({
        "ProductIntelligence/ProductIntelligence.exe": b"main",
        "ProductIntelligence/ProductIntelligenceUpdater.exe": b"updater",
        "ProductIntelligence/_internal/runtime.txt": b"runtime",
    }))
    root = recovery_updater.safe_extract_bundle(archive, tmp_path / "stage")
    assert root == tmp_path / "stage" / "ProductIntelligence"


def test_safe_extract_bundle_rejects_path_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(_zip_bytes({"ProductIntelligence/../../evil.txt": b"evil"}))
    with pytest.raises(ValueError, match="unsafe archive"):
        recovery_updater.safe_extract_bundle(archive, tmp_path / "stage")


def test_terminate_stale_updaters_targets_only_updater_processes():
    calls = []

    class Result:
        returncode = 0

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    recovery_updater._terminate_stale_updaters(platform="nt", runner=runner)
    assert len(calls) == 1
    command = calls[0][0]
    assert command[:3] == ["powershell", "-NoProfile", "-Command"]
    script = command[3]
    assert "ProductIntelligenceUpdater*" in script
    assert "Stop-Process -Force" in script
    assert "ProductIntelligenceRecoveryUpdater" not in script


def test_recovery_calls_stale_updater_cleanup_before_copy():
    source = Path("src/product_intelligence/recovery_updater.py").read_text(encoding="utf-8")
    recover_body = source.split("def recover(", 1)[1].split("def _message", 1)[0]
    assert "_terminate_stale_updaters()" in recover_body
    assert recover_body.index("_terminate_stale_updaters()") < recover_body.index("_copy_tree(product_root, target_dir)")


def test_self_test_exits_zero_without_network():
    assert recovery_updater.main(["--self-test"]) == 0


def test_recovery_pyinstaller_spec_is_standalone_onefile():
    spec = Path("ProductIntelligenceRecovery.spec").read_text(encoding="utf-8")
    assert "run_recovery_updater.py" in spec
    assert "ProductIntelligenceRecoveryUpdater" in spec
    assert "exclude_binaries=False" in spec
    assert "COLLECT(" not in spec


def test_windows_workflow_builds_and_smokes_recovery_exe():
    workflow = Path(".github/workflows/build-recovery-updater.yml").read_text(encoding="utf-8")
    assert "windows-latest" in workflow
    assert "ProductIntelligenceRecovery.spec" in workflow
    assert "ProductIntelligenceRecoveryUpdater.exe" in workflow
    assert "RUNNER_TEMP" in workflow
    assert "--self-test" in workflow
    assert "ProductIntelligenceRecoveryUpdater-Windows" in workflow
