from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .models import ProductIdentity


UPCITEMDB_LOOKUP_URL = "https://api.upcitemdb.com/prod/trial/lookup"
_SUCCESS_TTL_SECONDS = 30 * 24 * 60 * 60
_NOT_FOUND_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class UpcLookupResult:
    status: str
    identifier: str
    identity: ProductIdentity | None
    source: str
    rate_limit_limit: int | None = None
    rate_limit_remaining: int | None = None
    rate_limit_reset: int | None = None
    error: str | None = None


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def canonical_trade_code(value: str | None) -> str:
    """Normalize UPC/EAN/GTIN variants to a comparable GTIN-14 shape."""
    digits = _digits(value)
    if 8 <= len(digits) <= 14:
        return digits.zfill(14)
    return digits


def trade_codes_equivalent(left: str | None, right: str | None) -> bool:
    a = canonical_trade_code(left)
    b = canonical_trade_code(right)
    return bool(a and b and a == b)


def _default_cache_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else (Path.home() / ".product_intelligence")
    return root / "ProductIntelligence" / "identity_provider_cache.json" if base else root / "identity_provider_cache.json"


def _int_header(headers: Any, name: str) -> int | None:
    try:
        raw = headers.get(name)
        return int(raw) if raw not in (None, "") else None
    except Exception:
        return None


def _identity_from_item(item: dict) -> ProductIdentity:
    title = str(item.get("title") or "").strip() or None
    brand = str(item.get("brand") or "").strip() or None
    model = str(item.get("model") or "").strip() or None
    return ProductIdentity(
        brand=brand,
        manufacturer=brand,
        product_name=title,
        model=model or title,
        ean=str(item.get("ean") or "").strip() or None,
        upc=str(item.get("upc") or "").strip() or None,
        gtin=str(item.get("gtin") or "").strip() or None,
        confidence=.82 if brand and (model or title) else .65,
        match_level="HIGH" if brand and (model or title) else "MEDIUM",
    )


class UpcItemDbIdentityProvider:
    """Small fail-open UPC/EAN/GTIN identity provider with persistent cache.

    It never retries 429/5xx in a loop. The caller decides whether to continue with
    web identity discovery. Successful lookups are cached for 30 days and NOT_FOUND
    for 24 hours to protect the FREE daily/burst budget.
    """

    def __init__(self, *, cache_path: str | Path | None = None, session: requests.Session | None = None):
        self.cache_path = Path(cache_path) if cache_path else _default_cache_path()
        self.session = session or requests.Session()

    def _load_cache(self) -> dict:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _write_cache(self, payload: dict) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.cache_path)
        except Exception:
            # Cache failure must never make identity resolution fail.
            return

    @staticmethod
    def _cache_key(identifier: str) -> str:
        return f"upcitemdb:{canonical_trade_code(identifier) or _digits(identifier)}"

    def _cached(self, identifier: str) -> UpcLookupResult | None:
        cache = self._load_cache()
        row = cache.get(self._cache_key(identifier))
        if not isinstance(row, dict) or float(row.get("expires_at") or 0) <= time.time():
            return None
        identity_payload = row.get("identity")
        identity = ProductIdentity(**identity_payload) if isinstance(identity_payload, dict) else None
        return UpcLookupResult(
            status=str(row.get("status") or "UNAVAILABLE"),
            identifier=identifier,
            identity=identity,
            source="CACHE",
            rate_limit_limit=row.get("rate_limit_limit"),
            rate_limit_remaining=row.get("rate_limit_remaining"),
            rate_limit_reset=row.get("rate_limit_reset"),
            error=row.get("error"),
        )

    def _store(self, result: UpcLookupResult, ttl: int) -> None:
        cache = self._load_cache()
        cache[self._cache_key(result.identifier)] = {
            "status": result.status,
            "identity": result.identity.model_dump() if result.identity is not None else None,
            "stored_at": int(time.time()),
            "expires_at": int(time.time()) + int(ttl),
            "rate_limit_limit": result.rate_limit_limit,
            "rate_limit_remaining": result.rate_limit_remaining,
            "rate_limit_reset": result.rate_limit_reset,
            "error": result.error,
        }
        self._write_cache(cache)

    def lookup(self, identifier: str, *, timeout: int = 7) -> UpcLookupResult:
        raw = _digits(identifier)
        if not raw or not (8 <= len(raw) <= 14):
            return UpcLookupResult("INVALID", str(identifier or ""), None, "LOCAL", error="invalid_trade_code")

        cached = self._cached(raw)
        if cached is not None:
            return cached

        try:
            response = self.session.get(
                UPCITEMDB_LOOKUP_URL,
                params={"upc": raw},
                headers={"Accept": "application/json", "Accept-Encoding": "gzip, deflate"},
                timeout=(min(4, max(1, int(timeout))), min(7, max(2, int(timeout)))),
            )
        except requests.RequestException as exc:
            return UpcLookupResult("UNAVAILABLE", raw, None, "HTTP", error=f"{type(exc).__name__}: {exc}")

        limit = _int_header(response.headers, "X-RateLimit-Limit")
        remaining = _int_header(response.headers, "X-RateLimit-Remaining")
        reset = _int_header(response.headers, "X-RateLimit-Reset")

        if response.status_code == 404:
            result = UpcLookupResult("NOT_FOUND", raw, None, "HTTP", limit, remaining, reset)
            self._store(result, _NOT_FOUND_TTL_SECONDS)
            return result
        if response.status_code == 429:
            return UpcLookupResult("UNAVAILABLE", raw, None, "HTTP", limit, remaining, reset, "rate_limited")
        if response.status_code != 200:
            return UpcLookupResult("UNAVAILABLE", raw, None, "HTTP", limit, remaining, reset, f"http_{response.status_code}")

        try:
            payload = response.json()
        except Exception as exc:
            return UpcLookupResult("UNAVAILABLE", raw, None, "HTTP", limit, remaining, reset, f"invalid_json:{type(exc).__name__}")

        items = payload.get("items") if isinstance(payload, dict) else None
        if str(payload.get("code") if isinstance(payload, dict) else "").upper() != "OK" or not isinstance(items, list) or not items:
            result = UpcLookupResult("NOT_FOUND", raw, None, "HTTP", limit, remaining, reset)
            self._store(result, _NOT_FOUND_TTL_SECONDS)
            return result

        identity = _identity_from_item(items[0] if isinstance(items[0], dict) else {})
        result = UpcLookupResult("OK", raw, identity, "HTTP", limit, remaining, reset)
        self._store(result, _SUCCESS_TTL_SECONDS)
        return result


_DEFAULT_PROVIDER: UpcItemDbIdentityProvider | None = None


def lookup_identity_by_trade_code(identifier: str, *, timeout: int = 7) -> UpcLookupResult:
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is None:
        _DEFAULT_PROVIDER = UpcItemDbIdentityProvider()
    return _DEFAULT_PROVIDER.lookup(identifier, timeout=timeout)
