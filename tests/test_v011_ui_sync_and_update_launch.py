from pathlib import Path


ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "product_intelligence"


def test_final_shell_refreshes_media_and_price_lists_after_async_analysis():
    source = (SRC / "workspace_desktop.py").read_text(encoding="utf-8")
    assert "def _refresh_shared_product_consumers" in source
    apply_body = source.split("def _apply_analysis_result", 1)[1].split("\n    def ", 1)[0]
    assert "super()._apply_analysis_result(data)" in apply_body
    assert "self._refresh_shared_product_consumers()" in apply_body
    assert 'media_list = getattr(self, "media_product_list", None)' in source
    assert 'price_list = getattr(self, "price_product_list", None)' in source
    assert 'productos listos para multimedia' in source
    assert 'productos listos para comparar precios' in source


def test_shared_product_labels_support_sku_fallback():
    source = (SRC / "workspace_desktop.py").read_text(encoding="utf-8")
    assert "identity.sku" in source


def test_main_app_launches_updater_independently_with_windows_uac():
    provider = (SRC / "provider_desktop.py").read_text(encoding="utf-8")
    assert "def _launch_updater_process" in provider
    assert "ShellExecuteW" in provider
    assert '"runas"' in provider
    assert "subprocess.list2cmdline" in provider
    assert "UAC_ELEVATION_CANCELLED" in provider
