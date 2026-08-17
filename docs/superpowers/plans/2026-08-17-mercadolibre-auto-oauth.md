# Mercado Libre automatic persistent OAuth — v0.10.28

## Scope

Replace only Mercado Libre authentication/HTTP transport. Preserve the existing price discovery, parsing, identity scoring, dedupe, outlier filtering, channel coverage and all non-Mercado-Libre sources.

## Existing architecture found

- `price_workflow._try_mercadolibre()` calls Mercado Libre directly with `requests.get()`.
- `price_adapters.parse_mercadolibre_payload()` owns price parsing and identity acceptance and must remain unchanged.
- `key_store.py` already persists secrets through OS keyring / Windows Credential Manager.
- `ProviderSettings` persists non-secret desktop settings.
- `provider_desktop.py` already provides provider configuration UI and uses worker threads for network probes.

## Design

### MercadoLibreTokenStore

Persist one JSON OAuth state as a single keyring credential (`mercadolibre_oauth_state`) so refresh-token rotation cannot leave access/refresh/expiry split across separate writes. The state contains client id, client secret, access token, refresh token, absolute UTC `expires_at`, token type, user id, site id and updated-at. Never log the payload.

### MercadoLibreAuthService

- `get_valid_access_token()` returns a cached token only when it remains valid beyond a 10-minute safety margin.
- Missing/expired/near-expiry token triggers refresh.
- Refresh uses `POST https://api.mercadolibre.com/oauth/token` with form-urlencoded body.
- A process-local lock serializes refreshes; state is re-read/re-checked after taking the lock so concurrent callers cause only one HTTP refresh.
- Persist the newly returned access token and rotated refresh token together only after a successful response.
- Failed refresh preserves the previous credential state.
- `force_refresh()` is used by the manual button and one-time 401 recovery.

### MercadoLibreApiClient

- Before authenticated calls, gets a valid token from the auth service and attaches `Authorization: Bearer ...`.
- On one unexpected 401, force-refreshes once and retries once.
- A second 401 raises controlled `ERROR_AUTH_MERCADOLIBRE`; no retry loop.
- `/users/me` test connection uses this same client.

### Price integration

`_try_mercadolibre()` keeps its current queries and parser but delegates HTTP GET to `MercadoLibreApiClient`. No changes to price acceptance/ranking logic.

### Desktop configuration

Add a Mercado Libre provider card to Configuración:
- App ID / Client ID
- Client Secret (masked)
- Refresh Token (masked)
- optional Access Token (masked)
- Save / Configure
- Test connection
- Renew token now
- status, expiry, user id and site id

On first save, persist the supplied bootstrap credentials and immediately refresh to establish access token + absolute expiry. On later launches, a background startup validation refreshes only when required. JIT validation before API calls remains the correctness guarantee.

## Required tests

T1 valid token -> no refresh.
T2 expired -> refresh and persist rotated access/refresh.
T3 persisted expiry from yesterday -> refresh after reconstructed service/startup.
T4 near expiry -> refresh.
T5 hours remaining -> no refresh.
T6 401 -> one refresh + one retry -> 200.
T7 second 401 -> controlled failure, no loop.
T8 rotated refresh token persisted.
T9 failed refresh preserves previous state.
T10 concurrent requests -> one real refresh.
T11 secrets absent from sanitized diagnostics.
T12 existing Mercado Libre price parser/business logic unchanged and price workflow delegates transport through the client.

## Release gates

Focused OAuth tests -> full CI -> existing Price Intelligence smoke -> version 0.10.28 -> same-head CI -> merge to `release/windows` -> Windows Release success -> verify published ZIP + SHA256.