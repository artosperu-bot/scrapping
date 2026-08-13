from product_intelligence.provider_settings import ProviderSettings


def test_provider_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = ProviderSettings(path)
    settings.set("ocr_space_enabled", True)
    settings.set("mistral_enabled", True)
    settings.set("mistral_model", "mistral-small-latest")
    settings.set("request_timeout", 20)
    settings.save()

    loaded = ProviderSettings(path)
    assert loaded.get("ocr_space_enabled") is True
    assert loaded.get("mistral_enabled") is True
    assert loaded.get("mistral_model") == "mistral-small-latest"
    assert loaded.get("request_timeout") == 20


def test_provider_settings_defaults_when_file_missing(tmp_path):
    settings = ProviderSettings(tmp_path / "missing.json")
    assert settings.get("ocr_space_enabled") is True
    assert settings.get("mistral_enabled") is True
    assert settings.get("mistral_model") == "mistral-small-latest"
