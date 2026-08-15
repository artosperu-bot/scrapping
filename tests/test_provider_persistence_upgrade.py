from pathlib import Path


def test_provider_credentials_live_outside_install_tree():
    provider_settings_source = Path("src/product_intelligence/provider_settings.py").read_text(encoding="utf-8")
    key_store_source = Path("src/product_intelligence/key_store.py").read_text(encoding="utf-8")
    updater_source = Path("src/product_intelligence/updater.py").read_text(encoding="utf-8")

    assert "LOCALAPPDATA" in provider_settings_source
    assert 'SERVICE = "ProductIntelligence"' in key_store_source
    assert "keyring.set_password" in key_store_source
    assert "settings.json" not in updater_source
    assert "ocr_space_api_key" not in provider_settings_source
    assert "mistral_api_key" not in provider_settings_source


def test_desktop_loads_saved_keys_instead_of_requiring_reentry():
    source = Path("src/product_intelligence/provider_desktop.py").read_text(encoding="utf-8")
    assert "load_value(_PROVIDER_KEYS[name])" in source
    assert "save_value(_PROVIDER_KEYS[provider], value)" in source
