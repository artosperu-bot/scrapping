from product_intelligence.provider_status import ProviderStatus


def test_provider_status_values_are_stable():
    assert ProviderStatus.CONNECTED.value == "CONNECTED"
    assert ProviderStatus.TIMEOUT.value == "TIMEOUT"
    assert ProviderStatus.AUTH_REJECTED.value == "AUTH_REJECTED"
