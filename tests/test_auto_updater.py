from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from product_intelligence.update_service import ReleaseInfo, UpdateService, is_newer_version
from product_intelligence.updater import UnsafeArchiveError, extract_product_bundle
from product_intelligence.version import APP_VERSION


class FakeResponse:
    def __init__(self, *, payload=None, content=b"", text="", status=200):
        self._payload = payload
        self.content = content
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected HTTP call")
        return self.responses.pop(0)


def _release_payload(tag="v0.10.6"):
    return {
        "tag_name": tag,
        "body": "Cambios de prueba",
        "html_url": "https://github.com/artosperu-bot/scrapping/releases/tag/" + tag,
        "prerelease": False,
        "draft": False,
        "assets": [
            {"name": "ProductIntelligence-Windows.zip", "browser_download_url": "https://example.invalid/ProductIntelligence-Windows.zip"},
            {"name": "ProductIntelligence-Windows.sha256", "browser_download_url": "https://example.invalid/ProductIntelligence-Windows.sha256"},
        ],
    }


def test_app_version_is_current_auto_updatable_version():
    assert APP_VERSION == "0.10.20"


def test_semver_comparison_is_numeric_not_lexicographic():
    assert is_newer_version("0.10.18", "0.10.17") is True
    assert is_newer_version("0.10.17", "0.10.16") is True
    assert is_newer_version("0.10.16", "0.10.15") is True
    assert is_newer_version("0.10.15", "0.10.14") is True
    assert is_newer_version("0.10.14", "0.10.13") is True
    assert is_newer_version("0.10.13", "0.10.12") is True
    assert is_newer_version("0.10.12", "0.10.11") is True
    assert is_newer_version("0.10.11", "0.10.10") is True
    assert is_newer_version("0.10.10", "0.10.9") is True
    assert is_newer_version("0.10.4", "0.10.4") is False
    assert is_newer_version("0.9.99", "0.10.4") is False
    assert is_newer_version("v1.0.0", "0.10.4") is True


def test_check_latest_returns_release_only_when_newer():
    session = FakeSession([FakeResponse(payload=_release_payload("v0.10.6"))])
    service = UpdateService(current_version="0.10.4", session=session)
    release = service.check_latest()
    assert release == ReleaseInfo(
        version="0.10.6",
        zip_url="https://example.invalid/ProductIntelligence-Windows.zip",
        sha256_url="https://example.invalid/ProductIntelligence-Windows.sha256",
        notes="Cambios de prueba",
        page_url="https://github.com/artosperu-bot/scrapping/releases/tag/v0.10.6",
    )
    same = UpdateService(current_version="0.10.4", session=FakeSession([FakeResponse(payload=_release_payload("v0.10.4"))]))
    assert same.check_latest() is None


def test_check_latest_requires_both_release_assets():
    payload = _release_payload()
    payload["assets"] = payload["assets"][:1]
    service = UpdateService(current_version="0.10.4", session=FakeSession([FakeResponse(payload=payload)]))
    assert service.check_latest() is None


def test_download_verified_checks_sha256(tmp_path):
    zip_bytes = b"valid release bytes"
    digest = hashlib.sha256(zip_bytes).hexdigest()
    session = FakeSession([FakeResponse(content=zip_bytes), FakeResponse(text=f"{digest}  ProductIntelligence-Windows.zip\n")])
    service = UpdateService(current_version="0.10.4", session=session)
    release = ReleaseInfo("0.10.6", "zip", "sha", "", "")
    path = service.download_verified(release, tmp_path)
    assert path.read_bytes() == zip_bytes
    assert path.name == "ProductIntelligence-Windows.zip"


def test_download_verified_rejects_digest_mismatch(tmp_path):
    service = UpdateService(current_version="0.10.4", session=FakeSession([FakeResponse(content=b"tampered"), FakeResponse(text=f"{'0' * 64}  ProductIntelligence-Windows.zip\n")]))
    with pytest.raises(ValueError, match="SHA256"):
        service.download_verified(ReleaseInfo("0.10.6", "zip", "sha", "", ""), tmp_path)


def _zip_bytes(entries):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return data.getvalue()


def test_extract_product_bundle_requires_expected_root_and_extracts(tmp_path):
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(_zip_bytes({
        "ProductIntelligence/ProductIntelligence.exe": b"main",
        "ProductIntelligence/ProductIntelligenceUpdater.exe": b"updater",
        "ProductIntelligence/_internal/x.txt": b"x",
    }))
    stage = tmp_path / "stage"
    root = extract_product_bundle(archive, stage)
    assert root == stage / "ProductIntelligence"
    assert (root / "ProductIntelligence.exe").read_bytes() == b"main"


def test_extract_product_bundle_rejects_path_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(_zip_bytes({"ProductIntelligence/../../evil.txt": b"evil"}))
    with pytest.raises(UnsafeArchiveError):
        extract_product_bundle(archive, tmp_path / "stage")


def test_windows_wait_uses_native_process_handle():
    source = Path("src/product_intelligence/updater.py").read_text(encoding="utf-8")
    assert "WaitForSingleObject" in source
    assert 'if os.name == "nt"' in source
    assert "_wait_windows_process(pid, timeout)" in source


def test_provider_desktop_exposes_manual_update_controls():
    source = Path("src/product_intelligence/provider_desktop.py").read_text(encoding="utf-8")
    assert "Actualizaciones" in source
    assert "Buscar actualizaciones" in source
    assert "Actualizar ahora" in source
    assert "APP_VERSION" in source


def test_pyinstaller_bundle_contains_external_updater():
    spec = Path("ProductIntelligence.spec").read_text(encoding="utf-8")
    assert "run_updater.py" in spec
    assert "ProductIntelligenceUpdater" in spec
    workflow = Path(".github/workflows/build-windows.yml").read_text(encoding="utf-8")
    assert "ProductIntelligenceUpdater.exe" in workflow


def test_updater_exe_is_standalone_when_copied_to_temp():
    spec = Path("ProductIntelligence.spec").read_text(encoding="utf-8")
    updater_block = spec.split("updater_exe = EXE(", 1)[1].split("\n)\n\ncoll = COLLECT", 1)[0]
    assert "updater_analysis.binaries" in updater_block
    assert "updater_analysis.datas" in updater_block
    assert "exclude_binaries=False" in updater_block


def test_release_workflow_smokes_standalone_updater_from_temp():
    workflow = Path(".github/workflows/release-windows.yml").read_text(encoding="utf-8")
    assert "Verify standalone updater bootstrap" in workflow
    assert "RUNNER_TEMP" in workflow
    assert "Start-Process" in workflow
    assert "ProductIntelligenceUpdater.exe" in workflow


def test_release_workflow_publishes_zip_and_checksum():
    workflow = Path(".github/workflows/release-windows.yml").read_text(encoding="utf-8")
    assert "release/windows" in workflow
    assert "ProductIntelligence-Windows.zip" in workflow
    assert "ProductIntelligence-Windows.sha256" in workflow
    assert "contents: write" in workflow
