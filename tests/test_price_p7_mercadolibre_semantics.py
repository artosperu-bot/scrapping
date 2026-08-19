import pytest

from product_intelligence.mercadolibre_oauth import MercadoLibreAuthError
from product_intelligence import price_workflow


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (MercadoLibreAuthError("ML_AUTH_NOT_CONFIGURED"), "ML_NOT_CONFIGURED"),
        (MercadoLibreAuthError("ML_REFRESH_TOKEN_INVALID", http_status=400), "ML_AUTH_FAILED"),
        (MercadoLibreAuthError("ML_CLIENT_CREDENTIALS_INVALID", http_status=401), "ML_AUTH_FAILED"),
        (MercadoLibreAuthError("ERROR_AUTH_MERCADOLIBRE", http_status=401), "ML_AUTH_FAILED"),
        (MercadoLibreAuthError("ML_AUTH_NETWORK_ERROR"), "ML_ACCESS_BLOCKED"),
        (MercadoLibreAuthError("ML_AUTH_HTTP_ERROR", http_status=403), "ML_ACCESS_BLOCKED"),
    ],
)
def test_mercadolibre_auth_failures_have_semantic_terminal_states(error, expected):
    assert price_workflow._mercadolibre_terminal_status(error) == expected
