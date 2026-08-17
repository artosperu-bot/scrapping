from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest


class MemoryStore:
    def __init__(self, state=None):
        self.state = state
        self.save_count = 0

    def load(self):
        return self.state

    def save(self, state):
        self.state = state
        self.save_count += 1

    def clear(self):
        self.state = None


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = RuntimeError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class FakeSession:
    def __init__(self, *, posts=None, requests=None, post_delay=0):
        self.posts = list(posts or [])
        self.requests = list(requests or [])
        self.post_calls = []
        self.request_calls = []
        self.post_delay = post_delay
        self._lock = threading.Lock()

    def post(self, url, **kwargs):
        with self._lock:
            self.post_calls.append((url, kwargs))
            if not self.posts:
                raise AssertionError("unexpected token refresh")
            response = self.posts.pop(0)
        if self.post_delay:
            time.sleep(self.post_delay)
        if isinstance(response, Exception):
            raise response
        return response

    def request(self, method, url, **kwargs):
        with self._lock:
            self.request_calls.append((method, url, kwargs))
            if not self.requests:
                raise AssertionError("unexpected API request")
            response = self.requests.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def state(*, now, access="access-old", refresh="refresh-old", expires_delta=timedelta(hours=3)):
    from product_intelligence.mercadolibre_oauth import MercadoLibreOAuthState

    return MercadoLibreOAuthState(
        client_id="app-123",
        client_secret="secret-xyz",
        access_token=access,
        refresh_token=refresh,
        expires_at=(now + expires_delta).isoformat(),
        token_type="bearer",
    )


def token_payload(access="access-new", refresh="refresh-new", expires_in=21600):
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": expires_in,
        "token_type": "bearer",
        "user_id": 123456,
    }


def service(store, session, now):
    from product_intelligence.mercadolibre_oauth import MercadoLibreAuthService

    return MercadoLibreAuthService(store=store, session=session, now=lambda: now, refresh_margin=timedelta(minutes=10))


def test_t1_valid_token_is_reused_without_refresh():
    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    store = MemoryStore(state(now=now, expires_delta=timedelta(hours=3)))
    session = FakeSession()
    assert service(store, session, now).get_valid_access_token() == "access-old"
    assert session.post_calls == []


def test_t2_expired_token_refreshes_and_persists_rotated_tokens_and_absolute_expiry():
    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    store = MemoryStore(state(now=now, expires_delta=timedelta(hours=-1)))
    session = FakeSession(posts=[FakeResponse(200, token_payload())])
    token = service(store, session, now).get_valid_access_token()
    assert token == "access-new"
    assert store.state.access_token == "access-new"
    assert store.state.refresh_token == "refresh-new"
    assert utc(store.state.expires_at) == now + timedelta(seconds=21600)
    assert store.state.user_id == 123456
    assert len(session.post_calls) == 1
    _, call = session.post_calls[0]
    assert call["data"]["grant_type"] == "refresh_token"
    assert call["data"]["client_id"] == "app-123"
    assert call["data"]["client_secret"] == "secret-xyz"
    assert call["data"]["refresh_token"] == "refresh-old"


def test_t3_persisted_expiry_from_yesterday_refreshes_after_service_reconstruction():
    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    store = MemoryStore(state(now=now, expires_delta=timedelta(days=-1)))
    session = FakeSession(posts=[FakeResponse(200, token_payload())])
    reconstructed = service(store, session, now)
    assert reconstructed.get_valid_access_token() == "access-new"
    assert len(session.post_calls) == 1


def test_t4_near_expiry_inside_ten_minute_margin_refreshes():
    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    store = MemoryStore(state(now=now, expires_delta=timedelta(minutes=5)))
    session = FakeSession(posts=[FakeResponse(200, token_payload())])
    assert service(store, session, now).get_valid_access_token() == "access-new"
    assert len(session.post_calls) == 1


def test_t5_token_with_hours_remaining_does_not_refresh():
    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    store = MemoryStore(state(now=now, expires_delta=timedelta(hours=2)))
    session = FakeSession()
    assert service(store, session, now).get_valid_access_token() == "access-old"
    assert len(session.post_calls) == 0


def test_t6_unexpected_401_forces_one_refresh_and_retries_once():
    from product_intelligence.mercadolibre_oauth import MercadoLibreApiClient

    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    store = MemoryStore(state(now=now))
    session = FakeSession(posts=[FakeResponse(200, token_payload())], requests=[FakeResponse(401), FakeResponse(200, {"ok": True})])
    response = MercadoLibreApiClient(auth=service(store, session, now), session=session).request("GET", "/users/me")
    assert response.status_code == 200
    assert len(session.post_calls) == 1
    assert len(session.request_calls) == 2
    assert session.request_calls[0][2]["headers"]["Authorization"] == "Bearer access-old"
    assert session.request_calls[1][2]["headers"]["Authorization"] == "Bearer access-new"


def test_t7_second_401_is_controlled_and_never_loops():
    from product_intelligence.mercadolibre_oauth import MercadoLibreApiClient, MercadoLibreAuthError

    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    store = MemoryStore(state(now=now))
    session = FakeSession(posts=[FakeResponse(200, token_payload())], requests=[FakeResponse(401), FakeResponse(401)])
    with pytest.raises(MercadoLibreAuthError) as exc:
        MercadoLibreApiClient(auth=service(store, session, now), session=session).request("GET", "/users/me")
    assert exc.value.code == "ERROR_AUTH_MERCADOLIBRE"
    assert len(session.post_calls) == 1
    assert len(session.request_calls) == 2


def test_t8_rotated_refresh_token_is_persisted():
    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    store = MemoryStore(state(now=now, expires_delta=timedelta(hours=-1)))
    session = FakeSession(posts=[FakeResponse(200, token_payload(refresh="refresh-rotated"))])
    service(store, session, now).get_valid_access_token()
    assert store.state.refresh_token == "refresh-rotated"


def test_t9_failed_refresh_preserves_previous_persisted_credentials_and_hides_secrets():
    from product_intelligence.mercadolibre_oauth import MercadoLibreAuthError

    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    previous = state(now=now, expires_delta=timedelta(hours=-1))
    store = MemoryStore(previous)
    session = FakeSession(posts=[FakeResponse(400, {"error": "invalid_grant", "message": "bad refresh"})])
    with pytest.raises(MercadoLibreAuthError) as exc:
        service(store, session, now).get_valid_access_token()
    assert exc.value.code == "ML_REFRESH_TOKEN_INVALID"
    assert store.state == previous
    assert store.save_count == 0
    assert "refresh-old" not in str(exc.value)
    assert "secret-xyz" not in str(exc.value)


def test_t10_concurrent_expired_callers_perform_only_one_http_refresh():
    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    store = MemoryStore(state(now=now, expires_delta=timedelta(hours=-1)))
    session = FakeSession(posts=[FakeResponse(200, token_payload())], post_delay=0.05)
    auth = service(store, session, now)
    results, errors = [], []

    def worker():
        try:
            results.append(auth.get_valid_access_token())
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert errors == []
    assert results == ["access-new", "access-new"]
    assert len(session.post_calls) == 1


def test_token_store_serializes_all_oauth_state_inside_one_keyring_value(monkeypatch):
    from product_intelligence import mercadolibre_oauth as ml

    vault = {}
    monkeypatch.setattr(ml, "load_value", lambda key: vault.get(key))
    monkeypatch.setattr(ml, "save_value", lambda key, value: vault.__setitem__(key, value))
    monkeypatch.setattr(ml, "delete_value", lambda key: vault.pop(key, None))
    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    store = ml.MercadoLibreTokenStore()
    current = state(now=now)
    store.save(current)
    persisted = json.loads(vault[ml.ML_OAUTH_STATE_KEY])
    assert persisted["client_id"] == "app-123"
    assert persisted["client_secret"] == "secret-xyz"
    assert persisted["access_token"] == "access-old"
    assert persisted["refresh_token"] == "refresh-old"
    assert store.load() == current


def test_configure_refreshes_immediately_and_does_not_destroy_previous_working_state_on_failure():
    from product_intelligence.mercadolibre_oauth import MercadoLibreAuthError

    now = datetime(2026, 8, 17, 3, 0, tzinfo=timezone.utc)
    previous = state(now=now)
    store = MemoryStore(previous)
    session = FakeSession(posts=[FakeResponse(400, {"error": "invalid_grant"})])
    with pytest.raises(MercadoLibreAuthError):
        service(store, session, now).configure(client_id="new-app", client_secret="new-secret", refresh_token="new-refresh")
    assert store.state == previous


def test_price_workflow_delegates_mercadolibre_http_to_api_client_without_changing_queries(monkeypatch):
    from product_intelligence import price_workflow
    from product_intelligence.models import ProductIdentity

    identity = ProductIdentity(brand="Example", model="Model X", mpn="PART-123")
    calls = []

    class Client:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(200, {"results": []})

    monkeypatch.setattr(price_workflow, "build_mercadolibre_api_client", lambda timeout=15: Client())
    assert price_workflow._try_mercadolibre(identity, timeout=7) == []
    assert len(calls) == len(price_workflow._mercadolibre_queries(identity))
    assert all("api.mercadolibre.com/sites/MPE/search" in url for url, _ in calls)


def test_packaged_settings_ui_exposes_one_time_mercadolibre_configuration_and_auto_refresh_contract():
    from pathlib import Path

    mixin = Path("src/product_intelligence/mercadolibre_desktop.py").read_text(encoding="utf-8")
    final_shell = Path("src/product_intelligence/final_live_ui_desktop.py").read_text(encoding="utf-8")
    for text in ["Mercado Libre API", "Client ID / App ID", "Client Secret", "Refresh Token", "Probar conexión", "Renovar token ahora"]:
        assert text in mixin
    assert "MercadoLibreAuthService" in mixin
    assert "MercadoLibreApiClient" in mixin
    assert "_start_ml_startup_validation" in mixin
    assert "MercadoLibreDesktopMixin" in final_shell
