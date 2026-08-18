from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urljoin

import requests

from .key_store import delete_value, load_value, save_value

ML_OAUTH_STATE_KEY = "mercadolibre_oauth_state"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_API_BASE = "https://api.mercadolibre.com/"
DEFAULT_REFRESH_MARGIN = timedelta(minutes=10)


@dataclass(frozen=True)
class MercadoLibreOAuthState:
    client_id: str
    client_secret: str
    refresh_token: str
    access_token: str = ""
    expires_at: str = ""
    token_type: str = "bearer"
    user_id: int | None = None
    site_id: str | None = None
    updated_at: str = ""


class MercadoLibreAuthError(RuntimeError):
    def __init__(self, code: str, message: str = "", *, http_status: int | None = None):
        self.code = str(code)
        self.http_status = http_status
        clean_message = str(message or "").strip()
        super().__init__(f"{self.code}: {clean_message}" if clean_message else self.code)


class MercadoLibreTokenStore:
    """Persist the complete OAuth state as one credential-manager value.

    Keeping access token, rotated refresh token and absolute expiry in one JSON
    payload gives the refresh operation one persistent write boundary while still
    keeping every secret outside settings.json, logs, Excel and audit output.
    """

    def __init__(self, key: str = ML_OAUTH_STATE_KEY):
        self.key = key
        self._volatile_state: MercadoLibreOAuthState | None = None

    @staticmethod
    def _environment_state() -> MercadoLibreOAuthState | None:
        client_id = str(os.environ.get("MERCADOLIBRE_CLIENT_ID") or "").strip()
        client_secret = str(os.environ.get("MERCADOLIBRE_CLIENT_SECRET") or "").strip()
        refresh_token = str(os.environ.get("MERCADOLIBRE_REFRESH_TOKEN") or "").strip()
        access_token = str(os.environ.get("MERCADOLIBRE_ACCESS_TOKEN") or "").strip()
        if not any((client_id, client_secret, refresh_token, access_token)):
            return None
        return MercadoLibreOAuthState(
            client_id=client_id, client_secret=client_secret, refresh_token=refresh_token, access_token=access_token,
            expires_at=str(os.environ.get("MERCADOLIBRE_EXPIRES_AT") or "").strip(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def load(self) -> MercadoLibreOAuthState | None:
        if self._volatile_state is not None:
            return self._volatile_state
        try:
            raw = load_value(self.key)
        except Exception:
            raw = None
        if not raw:
            return self._environment_state()
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None
            return MercadoLibreOAuthState(
                client_id=str(data.get("client_id") or ""),
                client_secret=str(data.get("client_secret") or ""),
                refresh_token=str(data.get("refresh_token") or ""),
                access_token=str(data.get("access_token") or ""),
                expires_at=str(data.get("expires_at") or ""),
                token_type=str(data.get("token_type") or "bearer"),
                user_id=_optional_int(data.get("user_id")),
                site_id=_optional_text(data.get("site_id")),
                updated_at=str(data.get("updated_at") or ""),
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return self._environment_state()

    def save(self, state: MercadoLibreOAuthState) -> None:
        self._volatile_state = state
        try:
            save_value(self.key, json.dumps(asdict(state), ensure_ascii=False, separators=(",", ":")))
        except Exception:
            return

    def clear(self) -> None:
        self._volatile_state = None
        try:
            delete_value(self.key)
        except Exception:
            return


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_expiry(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


class MercadoLibreAuthService:
    def __init__(
        self,
        *,
        store: MercadoLibreTokenStore | Any | None = None,
        session: Any | None = None,
        now: Callable[[], datetime] | None = None,
        refresh_margin: timedelta = DEFAULT_REFRESH_MARGIN,
        timeout: int = 20,
    ):
        self.store = store or MercadoLibreTokenStore()
        self.session = session or requests.Session()
        self.now = now or _utc_now
        self.refresh_margin = max(timedelta(0), refresh_margin)
        self.timeout = max(1, int(timeout))
        self._refresh_lock = threading.Lock()

    def is_configured(self) -> bool:
        state = self.store.load()
        return bool(state and state.client_id and state.client_secret and state.refresh_token)

    def current_state(self) -> MercadoLibreOAuthState | None:
        return self.store.load()

    def get_valid_access_token(self) -> str:
        current = self._require_configured(self.store.load())
        if not self._needs_refresh(current):
            return current.access_token

        with self._refresh_lock:
            # Another caller may have refreshed and rotated the refresh token while
            # this caller was waiting. Re-read and re-check after taking the lock.
            current = self._require_configured(self.store.load())
            if not self._needs_refresh(current):
                return current.access_token
            refreshed = self._refresh_state(current)
            self.store.save(refreshed)
            return refreshed.access_token

    def force_refresh(self) -> str:
        with self._refresh_lock:
            current = self._require_configured(self.store.load())
            refreshed = self._refresh_state(current)
            self.store.save(refreshed)
            return refreshed.access_token

    def configure(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        access_token: str = "",
    ) -> MercadoLibreOAuthState:
        candidate = MercadoLibreOAuthState(
            client_id=str(client_id or "").strip(),
            client_secret=str(client_secret or "").strip(),
            refresh_token=str(refresh_token or "").strip(),
            access_token=str(access_token or "").strip(),
        )
        self._require_configured(candidate)
        # Validate/establish the chain before replacing a working persisted state.
        # A network or credential failure therefore leaves the old configuration
        # untouched rather than destroying a valid refresh-token chain.
        with self._refresh_lock:
            refreshed = self._refresh_state(candidate)
            self.store.save(refreshed)
            return refreshed

    def update_profile(self, *, user_id: Any = None, site_id: Any = None) -> MercadoLibreOAuthState:
        with self._refresh_lock:
            current = self._require_configured(self.store.load())
            updated = replace(
                current,
                user_id=_optional_int(user_id) if user_id is not None else current.user_id,
                site_id=_optional_text(site_id) if site_id is not None else current.site_id,
                updated_at=_as_utc(self.now()).isoformat(),
            )
            self.store.save(updated)
            return updated

    def _needs_refresh(self, state: MercadoLibreOAuthState) -> bool:
        if not state.access_token:
            return True
        expiry = _parse_expiry(state.expires_at)
        if expiry is None:
            # Unknown expiry is not proof of expiry. Use the token once; a 401 causes
            # the API client to refresh and retry exactly once.
            return False
        return _as_utc(self.now()) >= expiry - self.refresh_margin

    @staticmethod
    def _require_configured(state: MercadoLibreOAuthState | None) -> MercadoLibreOAuthState:
        if state is None or not state.client_id or not state.client_secret or not state.refresh_token:
            raise MercadoLibreAuthError(
                "ML_AUTH_NOT_CONFIGURED",
                "Configura Client ID, Client Secret y Refresh Token en Configuración.",
            )
        return state

    def _refresh_state(self, state: MercadoLibreOAuthState) -> MercadoLibreOAuthState:
        data = {
            "grant_type": "refresh_token",
            "client_id": state.client_id,
            "client_secret": state.client_secret,
            "refresh_token": state.refresh_token,
        }
        try:
            response = self.session.post(
                ML_TOKEN_URL,
                data=data,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "ProductIntelligence/0.10",
                },
                timeout=self.timeout,
            )
        except Exception as exc:
            raise MercadoLibreAuthError("ML_AUTH_NETWORK_ERROR", type(exc).__name__) from None

        payload = self._safe_json(response)
        status = int(getattr(response, "status_code", 0) or 0)
        if status < 200 or status >= 300:
            code = self._map_refresh_error(payload, status)
            message = str(payload.get("message") or payload.get("error_description") or payload.get("error") or "")
            raise MercadoLibreAuthError(code, message, http_status=status)

        access_token = str(payload.get("access_token") or "").strip()
        if not access_token:
            raise MercadoLibreAuthError("ML_AUTH_HTTP_ERROR", "Respuesta OAuth sin access_token", http_status=status)
        try:
            expires_in = int(payload.get("expires_in"))
        except (TypeError, ValueError):
            expires_in = 0
        if expires_in <= 0:
            raise MercadoLibreAuthError("ML_AUTH_HTTP_ERROR", "Respuesta OAuth sin expires_in válido", http_status=status)

        now = _as_utc(self.now())
        rotated_refresh = str(payload.get("refresh_token") or state.refresh_token).strip()
        if not rotated_refresh:
            raise MercadoLibreAuthError("ML_AUTH_HTTP_ERROR", "Respuesta OAuth sin refresh_token utilizable", http_status=status)

        return MercadoLibreOAuthState(
            client_id=state.client_id,
            client_secret=state.client_secret,
            access_token=access_token,
            refresh_token=rotated_refresh,
            expires_at=(now + timedelta(seconds=expires_in)).isoformat(),
            token_type=str(payload.get("token_type") or state.token_type or "bearer"),
            user_id=_optional_int(payload.get("user_id")) if payload.get("user_id") is not None else state.user_id,
            site_id=state.site_id,
            updated_at=now.isoformat(),
        )

    @staticmethod
    def _safe_json(response: Any) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _map_refresh_error(payload: dict[str, Any], status: int) -> str:
        error = str(payload.get("error") or "").lower()
        message = str(payload.get("message") or payload.get("error_description") or "").lower()
        text = f"{error} {message}"
        if "invalid_grant" in text or "refresh" in text and ("invalid" in text or "revoked" in text or "expired" in text):
            return "ML_REFRESH_TOKEN_INVALID"
        if "invalid_client" in text or "client" in text and ("secret" in text or "credential" in text):
            return "ML_CLIENT_CREDENTIALS_INVALID"
        if status in {401, 403}:
            return "ML_CLIENT_CREDENTIALS_INVALID"
        return "ML_AUTH_HTTP_ERROR"


class MercadoLibreApiClient:
    def __init__(
        self,
        *,
        auth: MercadoLibreAuthService | None = None,
        session: Any | None = None,
        timeout: int = 20,
    ):
        self.session = session or requests.Session()
        self.auth = auth or MercadoLibreAuthService(session=self.session, timeout=timeout)
        self.timeout = max(1, int(timeout))

    def request(self, method: str, url: str, **kwargs):
        request_url = self._absolute_url(url)
        timeout = kwargs.pop("timeout", self.timeout)
        headers = dict(kwargs.pop("headers", {}) or {})
        token = self.auth.get_valid_access_token()
        response = self._request_once(method, request_url, token, headers, timeout, kwargs)
        if int(getattr(response, "status_code", 0) or 0) != 401:
            return response

        refreshed = self.auth.force_refresh()
        response = self._request_once(method, request_url, refreshed, headers, timeout, kwargs)
        if int(getattr(response, "status_code", 0) or 0) == 401:
            raise MercadoLibreAuthError(
                "ERROR_AUTH_MERCADOLIBRE",
                "Mercado Libre rechazó el token después de un refresh y un reintento.",
                http_status=401,
            )
        return response

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def users_me(self) -> dict[str, Any]:
        response = self.get("/users/me")
        try:
            response.raise_for_status()
        except Exception:
            raise MercadoLibreAuthError(
                "ERROR_AUTH_MERCADOLIBRE",
                f"HTTP {getattr(response, 'status_code', 'unknown')}",
                http_status=getattr(response, "status_code", None),
            ) from None
        payload = response.json()
        if not isinstance(payload, dict):
            raise MercadoLibreAuthError("ERROR_AUTH_MERCADOLIBRE", "Respuesta inválida de /users/me")
        site_id = payload.get("site_id")
        user_id = payload.get("id")
        self.auth.update_profile(user_id=user_id, site_id=site_id)
        return payload

    def _request_once(self, method: str, url: str, token: str, headers: dict[str, str], timeout: int, kwargs: dict):
        request_headers = dict(headers)
        request_headers.setdefault("Accept", "application/json")
        request_headers.setdefault("User-Agent", "ProductIntelligence/0.10")
        request_headers["Authorization"] = f"Bearer {token}"
        try:
            return self.session.request(method, url, headers=request_headers, timeout=timeout, **kwargs)
        except Exception as exc:
            raise MercadoLibreAuthError("ML_AUTH_NETWORK_ERROR", type(exc).__name__) from None

    @staticmethod
    def _absolute_url(url: str) -> str:
        clean = str(url or "").strip()
        if clean.startswith(("http://", "https://")):
            return clean
        return urljoin(ML_API_BASE, clean.lstrip("/"))


def build_mercadolibre_api_client(*, timeout: int = 20) -> MercadoLibreApiClient:
    return MercadoLibreApiClient(timeout=timeout)
