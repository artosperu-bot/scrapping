from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _host(value: str) -> str:
    return (urlparse(str(value or "")).hostname or str(value or "")).casefold().removeprefix("www.").strip(" /")


def detect_ecommerce_platform(url: str, html: str | None = None) -> str:
    """Detect common ecommerce families from public implementation signals.

    Detection is intentionally domain-agnostic: learned domains may change platform,
    therefore this is re-evaluated whenever fresh page evidence is available.
    """
    text = str(html or "")
    lower = text.casefold()
    url_lower = str(url or "").casefold()
    if any(marker in lower for marker in ("vteximg", "/api/catalog_system/", "__runtime__", "vtexjs")):
        return "vtex"
    if any(marker in lower for marker in ("cdn.shopify.com", "shopify.theme", "shopify.shop")) or "/products/" in url_lower and ".myshopify.com" in url_lower:
        return "shopify"
    if any(marker in lower for marker in ("woocommerce", "wp-content/plugins/woocommerce", "wc-add-to-cart", "wc-block")):
        return "woocommerce"
    if any(marker in lower for marker in ("magento_", "mage/cookies", "mage-cache-storage", "x-magento-init")):
        return "magento"
    if re.search(r'<script[^>]+type=["\']application/ld\+json["\']', text, re.I) and re.search(r'["\']@type["\']\s*:\s*["\']Product["\']', text, re.I):
        return "jsonld"
    return "custom"


class SourceCapabilityRegistry:
    """Timestamped observations about price-source capabilities.

    This is memory, not policy: callers must still inspect the current page/source.
    """

    def __init__(self, output_root: str | Path) -> None:
        root = Path(output_root)
        self.path = root / "price_intelligence" / "source_capabilities.json"

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, domain: str) -> dict[str, Any] | None:
        return self._load().get(_host(domain))

    def all(self) -> dict[str, dict[str, Any]]:
        return self._load()

    def successful_domains(self, *, limit: int = 12) -> list[str]:
        """Return recently successful domains as a soft-priority lane, never a whitelist."""
        rows = []
        for domain, row in self._load().items():
            if int(row.get("success_count") or 0) <= 0:
                continue
            rows.append((str(row.get("last_success") or ""), float(row.get("success_rate") or 0), domain))
        rows.sort(reverse=True)
        return [domain for _last, _rate, domain in rows[: max(0, int(limit))]]

    def record(
        self,
        url_or_domain: str,
        *,
        platform: str | None = None,
        discovery_method: str | None = None,
        extraction_method: str | None = None,
        price_capable: bool | None = None,
        stock_capable: bool | None = None,
        seller_capable: bool | None = None,
        success: bool | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        domain = _host(url_or_domain)
        if not domain:
            raise ValueError("Source capability observation requires a domain")
        data = self._load()
        row = dict(data.get(domain) or {})
        row.setdefault("domain", domain)
        row.setdefault("country", "PE" if domain.endswith(".pe") or domain.endswith(".com.pe") else None)
        row.setdefault("categories", [])
        row.setdefault("discovery_methods", [])
        row.setdefault("extraction_methods", [])
        row.setdefault("success_count", 0)
        row.setdefault("failure_count", 0)
        row.setdefault("observation_count", 0)
        row["observation_count"] = int(row["observation_count"] or 0) + 1
        row["last_observed_at"] = datetime.now(timezone.utc).isoformat()
        if platform:
            row["platform"] = str(platform)
        for field, value in (("discovery_methods", discovery_method), ("extraction_methods", extraction_method), ("categories", category)):
            if value and value not in row[field]:
                row[field].append(value)
        for field, value in (("price_capable", price_capable), ("stock_capable", stock_capable), ("seller_capable", seller_capable)):
            if value is not None:
                row[field] = bool(value)
        if success is True:
            row["success_count"] = int(row["success_count"] or 0) + 1
            row["last_success"] = row["last_observed_at"]
        elif success is False:
            row["failure_count"] = int(row["failure_count"] or 0) + 1
        total = int(row["success_count"] or 0) + int(row["failure_count"] or 0)
        row["success_rate"] = round(int(row["success_count"] or 0) / total, 4) if total else None
        data[domain] = row
        self._save(data)
        return row