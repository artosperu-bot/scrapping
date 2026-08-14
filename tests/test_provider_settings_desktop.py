import inspect

from product_intelligence import provider_desktop


def test_single_configuration_workspace_is_present():
    source = inspect.getsource(provider_desktop.App)
    assert 'text="Configuración"' in source
    assert 'text="OCR.space"' in source
    assert 'text="Mistral"' in source
    assert 'mistral-small-latest' in source


def test_provider_keys_are_masked_and_real_connection_button_is_disabled():
    source = inspect.getsource(provider_desktop.App._provider_box)
    assert 'show="•"' in source
    assert 'Probar conexión · pendiente' in source
    assert 'state="disabled"' in source


def test_configuration_workspace_uses_existing_key_store_not_json_for_secrets():
    module_source = inspect.getsource(provider_desktop)
    assert "save_value(" in module_source
    assert "delete_value(" in module_source
    assert "ProviderSettings" in module_source
    assert "requests." not in module_source
