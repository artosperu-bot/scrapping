from pathlib import Path


ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "product_intelligence"


def test_media_and_price_refresh_after_async_analysis_result():
    media = (SRC / "media_desktop.py").read_text(encoding="utf-8")
    price = (SRC / "price_desktop.py").read_text(encoding="utf-8")

    assert "def _apply_analysis_result" in media
    assert "def _refresh_media_product_list" in media
    assert "super()._apply_analysis_result(data)" in media
    assert "self._refresh_media_product_list()" in media

    assert "def _apply_analysis_result" in price
    assert "def _refresh_price_product_list" in price
    assert "super()._apply_analysis_result(data)" in price
    assert "self._refresh_price_product_list()" in price


def test_media_and_price_labels_support_sku_fallback():
    media = (SRC / "media_desktop.py").read_text(encoding="utf-8")
    price = (SRC / "price_desktop.py").read_text(encoding="utf-8")
    assert "ident.sku" in media
    assert "ident.sku" in price


def test_main_app_launches_updater_as_independent_windows_process():
    provider = (SRC / "provider_desktop.py").read_text(encoding="utf-8")
    assert "def _updater_creationflags" in provider
    assert "CREATE_NEW_PROCESS_GROUP" in provider
    assert "DETACHED_PROCESS" in provider
    assert "creationflags=self._updater_creationflags()" in provider


def test_v011_release_version_contract():
    version_source = (SRC / "version.py").read_text(encoding="utf-8")
    project_source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'APP_VERSION = "0.10.11"' in version_source
    assert 'version = "0.10.11"' in project_source
