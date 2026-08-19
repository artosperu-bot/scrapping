from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from .models import ProductIdentity
from .product_classification import classify_product


def _host(value: str) -> str:
    return (urlparse(str(value or "")).hostname or str(value or "")).casefold().removeprefix("www.").strip(" /")


def _country_for_domain(domain: str) -> str | None:
    domain = _host(domain)
    if domain.endswith(".pe") or domain.endswith(".com.pe") or "peru" in domain:
        return "PE"
    return None


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
    """Persistent source capability evidence used by bounded routing policy.

    The registry stores how a source works, never a product answer or current price.
    Every direct route still performs a fresh source request and the normal identity,
    market, confidence, price-quality, and dedupe gates remain authoritative.
    """

    _DIRECT_PLATFORM_METHODS = {"vtex": "vtex_catalog"}

    def __init__(self, output_root: str | Path) -> None:
        root = Path(output_root)
        self.path = root / "price_intelligence" / "source_capabilities.json"
        self._write_lock = Lock()

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

    def direct_candidates(
        self,
        identity: ProductIdentity,
        *,
        limit: int = 8,
        exclude_domains: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        """Select learned sources that have a *proven* direct mechanism.

        Currently VTEX catalog search is the only source-native mechanism exposed by
        the price workflow that can start from a domain alone. Other remembered
        platforms stay in memory and continue through open-provider fallback until a
        source-native mechanism is separately demonstrated and tested.
        """
        classification = classify_product(identity)
        requested_category = str(classification.category or "GENERAL")
        strong_category = classification.confidence >= 0.80 and requested_category != "GENERAL"
        excluded = {_host(value) for value in exclude_domains if _host(value)}
        now = datetime.now(timezone.utc)
        candidates: list[tuple[float, str, dict[str, Any]]] = []

        for domain, raw in self._load().items():
            row = dict(raw or {})
            platform = str(row.get("platform") or "").casefold()
            direct_method = self._DIRECT_PLATFORM_METHODS.get(platform)
            successes = int(row.get("success_count") or 0)
            failures = int(row.get("failure_count") or 0)
            if not direct_method or successes <= 0 or domain in excluded:
                continue
            if row.get("price_capable") is False:
                continue

            categories = {str(value) for value in row.get("categories") or [] if str(value)}
            if strong_category and categories and "GENERAL" not in categories and requested_category not in categories:
                continue

            total = successes + failures
            success_rate = float(row.get("success_rate") if row.get("success_rate") is not None else (successes / total if total else 0.0))
            health = float(row.get("health") if row.get("health") is not None else ((successes + 1) / (total + 2)))
            score = (2.0 * success_rate) + health + min(successes, 3) * 0.25
            if row.get("price_capable") is True:
                score += 1.0
            if requested_category in categories:
                score += 1.5
            elif not categories or "GENERAL" in categories:
                score += 0.25
            last_success = str(row.get("last_success") or "")
            if last_success:
                try:
                    observed = datetime.fromisoformat(last_success.replace("Z", "+00:00"))
                    age_days = max(0.0, (now - observed.astimezone(timezone.utc)).total_seconds() / 86400.0)
                    if age_days <= 30:
                        score += 0.25
                    elif age_days <= 90:
                        score += 0.10
                except (ValueError, TypeError):
                    pass

            row.update({
                "domain": domain,
                "direct_method": direct_method,
                "source_recovery_method": "DIRECT_SOURCE",
                "routing_score": round(score, 4),
                "routing_category": requested_category,
                "routing_category_confidence": classification.confidence,
            })
            candidates.append((score, str(row.get("last_success") or ""), row))

        candidates.sort(key=lambda item: (item[0], item[1], item[2]["domain"]), reverse=True)
        return [row for _score, _last, row in candidates[: max(0, int(limit))]]

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
        with self._write_lock:
            data = self._load()
            row = dict(data.get(domain) or {})
            row.setdefault("domain", domain)
            row.setdefault("country", _country_for_domain(domain))
            row.setdefault("categories", [])
            row.setdefault("discovery_methods", [])
            row.setdefault("extraction_methods", [])
            row.setdefault("success_count", 0)
            row.setdefault("failure_count", 0)
            row.setdefault("observation_count", 0)
            row["observation_count"] = int(row["observation_count"] or 0) + 1
            row["last_observed_at"] = datetime.now(timezone.utc).isoformat()
            row["observed_at"] = row["last_observed_at"]
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
                row["last_failure"] = row["last_observed_at"]
            total = int(row["success_count"] or 0) + int(row["failure_count"] or 0)
            row["success_rate"] = round(int(row["success_count"] or 0) / total, 4) if total else None
            row["health"] = round((int(row["success_count"] or 0) + 1) / (total + 2), 4)
            data[domain] = row
            self._save(data)
            return row