from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _host(value: str) -> str:
    return (urlparse(str(value or "")).hostname or str(value or "")).lower().removeprefix("www.").strip("/")


def _country_for_host(host: str) -> str | None:
    host = str(host or "").lower()
    return "PE" if host.endswith(".pe") else None


def detect_platform(url: str, html: str) -> str:
    hay = f"{url}\n{html}".lower()
    if any(marker in hay for marker in ("vtex", "vteximg", "/api/catalog_system/", "__vtex")):
        return "vtex"
    if any(marker in hay for marker in ("shopify", "cdn.shopify.com", "shopify-checkout-api-token", "/products/")):
        return "shopify"
    if any(marker in hay for marker in ("woocommerce", "wc-ajax", "/wp-json/wc/", "woocommerce-")):
        return "woocommerce"
    if any(marker in hay for marker in ("mage/cookies", "magento", "mage-cache", "data-mage-init")):
        return "magento"
    if "application/ld+json" in hay and ('"@type":"product"' in hay.replace(" ", "") or "'@type':'product'" in hay.replace(" ", "")):
        return "jsonld"
    return "custom"


class SourceCapabilityRegistry:
    """Small timestamped memory of observed source capabilities.

    Observations are hints for future routing, never permanent truth. A later observation
    updates platform/capabilities and success rate instead of freezing an assumption.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.rows: dict[str, dict[str, Any]] = {}
        if self.path.is_file():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    values = payload.get("sources", payload)
                    if isinstance(values, dict):
                        self.rows = {str(k): dict(v) for k, v in values.items() if isinstance(v, dict)}
            except Exception:
                self.rows = {}

    def get(self, domain: str) -> dict[str, Any] | None:
        row = self.rows.get(_host(domain))
        return dict(row) if row else None

    def observe(
        self,
        url: str,
        *,
        platform: str | None = None,
        category: str | None = None,
        discovery_method: str | None = None,
        extraction_method: str | None = None,
        price_capable: bool | None = None,
        stock_capable: bool | None = None,
        seller_capable: bool | None = None,
        success: bool = False,
    ) -> dict[str, Any]:
        domain = _host(url)
        if not domain:
            raise ValueError("source domain is required")
        now = _utcnow()
        row = dict(self.rows.get(domain) or {})
        row.setdefault("domain", domain)
        row.setdefault("country", _country_for_host(domain))
        row.setdefault("categories", [])
        row.setdefault("discovery_methods", [])
        row.setdefault("extraction_methods", [])
        row.setdefault("observations", 0)
        row.setdefault("successes", 0)
        row["observations"] = int(row.get("observations") or 0) + 1
        if success:
            row["successes"] = int(row.get("successes") or 0) + 1
            row["last_success"] = now
        row["last_observed"] = now
        if platform:
            row["platform"] = str(platform)
        for field, value in (("categories", category), ("discovery_methods", discovery_method), ("extraction_methods", extraction_method)):
            if value:
                values = list(row.get(field) or [])
                if str(value) not in values:
                    values.append(str(value))
                row[field] = values
        for field, value in (("price_capable", price_capable), ("stock_capable", stock_capable), ("seller_capable", seller_capable)):
            if value is not None:
                row[field] = bool(value)
        observations = max(1, int(row.get("observations") or 1))
        row["success_rate"] = int(row.get("successes") or 0) / observations
        self.rows[domain] = row
        return dict(row)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "updated_at": _utcnow(), "sources": self.rows}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
