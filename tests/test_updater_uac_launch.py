from pathlib import Path


ROOT = Path(__file__).parents[1]
PROVIDER_DESKTOP = ROOT / "src" / "product_intelligence" / "provider_desktop.py"


def test_windows_update_launch_requests_uac_elevation():
    source = PROVIDER_DESKTOP.read_text(encoding="utf-8")
    assert "ShellExecuteW" in source
    assert '"runas"' in source
    assert "subprocess.list2cmdline" in source


def test_uac_cancel_does_not_close_current_installation():
    source = PROVIDER_DESKTOP.read_text(encoding="utf-8")
    assert "UAC_ELEVATION_CANCELLED" in source
    assert "shell_result <= 32" in source
