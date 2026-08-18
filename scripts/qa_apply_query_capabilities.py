from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"expected source block not found: {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


CAPABILITIES = r'''from __future__ import annotations

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
'''
Path("src/product_intelligence/price_source_capabilities.py").write_text(CAPABILITIES, encoding="utf-8")

# P2 query metrics at the boundary that actually sees raw and ranked results.
replace_once(
    "src/product_intelligence/discovery.py",
    'def search_web_query(identity:ProductIdentity,query:str,limit:int=6,timeout:int=8,budget_tracker:SearchBudgetTracker|None=None)->list[str]:\n'
    '    if not str(query or "").strip():return []\n'
    '    if budget_tracker is not None:\n'
    '        ranked=_budgeted_query(identity,str(query).strip(),timeout,budget_tracker)\n'
    '    else:\n'
    '        raw=_filter_query_domain(_provider_search(str(query).strip(),timeout),str(query).strip())\n'
    '        ranked=_rank_candidates(raw,identity,max(limit*2,limit))\n'
    '    return [row.url for row in ranked[:limit]]',
    'def search_web_query(identity:ProductIdentity,query:str,limit:int=6,timeout:int=8,budget_tracker:SearchBudgetTracker|None=None,on_event=None)->list[str]:\n'
    '    clean_query=str(query or "").strip()\n'
    '    if not clean_query:return []\n'
    '    domain=_query_domain_constraint(clean_query)\n'
    '    if budget_tracker is not None:\n'
    '        ranked=_budgeted_query(identity,clean_query,timeout,budget_tracker)\n'
    '        raw_count=None; valid_count=None\n'
    '    else:\n'
    '        raw_all=_provider_search(clean_query,timeout)\n'
    '        raw_count=len(raw_all)\n'
    '        raw=_filter_query_domain(raw_all,clean_query)\n'
    '        valid_count=len(raw)\n'
    '        ranked=_rank_candidates(raw,identity,max(limit*2,limit))\n'
    '    selected=ranked[:limit]\n'
    '    if on_event:\n'
    '        on_event({"stage":"QUERY_EXECUTED","query":clean_query,"domain":domain,"raw_results":raw_count,"valid_in_domain":valid_count,"ranked_results":len(selected)})\n'
    '    return [row.url for row in selected]',
)

# P2: directed queries use original + separator aliases and verified brand/model signals.
start = '''def _queries(identity: ProductIdentity, domain: str) -> list[str]:
    strong = _strong(identity)
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    q = [f'"{strong}" site:{domain}']
    if model:
        q += [f'"{strong}" "{model}" site:{domain}', f'"{model}" {brand} site:{domain}'.strip()]
'''
replacement = '''def _queries(identity: ProductIdentity, domain: str) -> list[str]:
    strong = _strong(identity)
    model = str(identity.model or identity.product_name or "").strip()
    brand = str(identity.brand or "").strip()
    aliases = _identifier_aliases(strong) or ([strong] if strong else [])
    q: list[str] = []
    for alias in aliases:
        q.append(f'"{alias}" site:{domain}')
        if brand:
            q.append(f'"{alias}" "{brand}" site:{domain}')
        if model:
            q.append(f'"{alias}" "{model}" site:{domain}')
    if model:
        q.append(f'"{model}" "{brand}" site:{domain}'.strip())
'''
replace_once("src/product_intelligence/price_peru_coverage.py", start, replacement)

# P3: bounded novelty-based target discovery with diagnostic callback.
old = '''def _discover_target_domain(identity: ProductIdentity, domain: str, limit_per_domain: int) -> list[str]:
    strong = _strong(identity)
    model = str(identity.model or identity.product_name or "").strip()
    alias_identity = _alias_identity(identity)
    found: list[str] = []
    seen: set[str] = set()
    for seed in _deterministic_pdps(identity):
        if _host_matches(seed, domain) and _is_pdp(seed, domain, strong):
            seen.add(seed)
            found.append(seed)
    for query in _queries(identity, domain):
        try:
            urls = search_web_query(identity, query, limit=limit_per_domain, timeout=12)
        except Exception:
            urls = []
        for raw in urls:
            url = str(raw or "").strip()
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            if not _host_matches(url, domain) or not _is_pdp(url, domain, strong):
                continue
            seen.add(url)
            found.append(url)
            if len(found) >= limit_per_domain:
                break
        if len(found) >= limit_per_domain:
            break
    if len(found) < limit_per_domain and model:
        for query in _alias_queries(identity, domain):
            try:
                urls = search_web_query(alias_identity, query, limit=limit_per_domain, timeout=12)
            except Exception:
                urls = []
            for raw in urls:
                url = str(raw or "").strip()
                if not url.startswith(("http://", "https://")) or url in seen:
                    continue
                if not _host_matches(url, domain) or not _is_pdp(url, domain, model):
                    continue
                seen.add(url)
                found.append(url)
                if len(found) >= limit_per_domain:
                    break
            if len(found) >= limit_per_domain:
                break
    return found
'''
new = '''def _discover_target_domain(identity: ProductIdentity, domain: str, limit_per_domain: int, *, on_event=None, max_queries: int = 6) -> list[str]:
    strong = _strong(identity)
    model = str(identity.model or identity.product_name or "").strip()
    alias_identity = _alias_identity(identity)
    found: list[str] = []
    seen: set[str] = set()
    query_count = 0
    no_gain_streak = 0

    def emit(stage: str, **payload) -> None:
        if on_event:
            on_event({"stage": stage, "domain": domain, **payload})

    for seed in _deterministic_pdps(identity):
        if _host_matches(seed, domain) and _is_pdp(seed, domain, strong):
            seen.add(seed)
            found.append(seed)
    if len(found) >= limit_per_domain:
        emit("DISCOVERY_STOP", reason="candidate_budget_full", total_pdps=len(found), queries=query_count)
        return found[:limit_per_domain]

    plans = [(identity, query, strong) for query in _queries(identity, domain)]
    if model:
        plans.extend((alias_identity, query, model) for query in _alias_queries(identity, domain))

    stop_reason = "query_plan_exhausted"
    for query_identity, query, marker in plans:
        if query_count >= max_queries:
            stop_reason = "query_budget_exhausted"
            break
        query_count += 1
        before = len(found)
        try:
            urls = search_web_query(query_identity, query, limit=limit_per_domain, timeout=12, on_event=on_event)
        except Exception as exc:
            urls = []
            emit("QUERY_EXECUTED", query=query, raw_results=None, valid_in_domain=None, ranked_results=0, error=f"{type(exc).__name__}: {exc}")
        for raw in urls:
            url = str(raw or "").strip()
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            if not _host_matches(url, domain) or not _is_pdp(url, domain, marker):
                continue
            seen.add(url)
            found.append(url)
            if len(found) >= limit_per_domain:
                break
        gain = len(found) - before
        emit("QUERY_INFORMATION_GAIN", query=query, new_urls=gain, new_pdps=gain, total_pdps=len(found), information_gain=gain)
        no_gain_streak = 0 if gain else no_gain_streak + 1
        if len(found) >= limit_per_domain:
            stop_reason = "candidate_budget_full"
            break
        if found and no_gain_streak >= 2:
            stop_reason = "no_new_pdps"
            break
    emit("DISCOVERY_STOP", reason=stop_reason, total_pdps=len(found), queries=query_count)
    return found
'''
replace_once("src/product_intelligence/price_peru_coverage.py", old, new)

# Propagate diagnostic callback while preserving old API.
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    'def discover_additional_peru_pdps(identity: ProductIdentity, *, limit_per_domain: int = 10, domains: tuple[str, ...] = PERU_MARKETPLACE_DOMAINS) -> list[str]:',
    'def discover_additional_peru_pdps(identity: ProductIdentity, *, limit_per_domain: int = 10, domains: tuple[str, ...] = PERU_MARKETPLACE_DOMAINS, on_event=None) -> list[str]:',
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    '        per_domain = list(pool.map(lambda domain: _discover_target_domain(identity, domain, limit_per_domain), domains))',
    '        per_domain = list(pool.map(lambda domain: _discover_target_domain(identity, domain, limit_per_domain, on_event=on_event), domains))',
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    'def _search_query_batches(identity: ProductIdentity, queries: list[str], per_query: int) -> list[list[str]]:',
    'def _search_query_batches(identity: ProductIdentity, queries: list[str], per_query: int, on_event=None) -> list[list[str]]:',
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    '            return search_web_query(identity, query, limit=per_query, timeout=12)',
    '            return search_web_query(identity, query, limit=per_query, timeout=12, on_event=on_event)',
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    'def discover_general_peru_retailers(identity: ProductIdentity, *, limit: int = 20) -> list[str]:',
    'def discover_general_peru_retailers(identity: ProductIdentity, *, limit: int = 20, on_event=None) -> list[str]:',
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    '    exact_batches = _search_query_batches(identity, _general_retail_queries(identity), per_query)',
    '    exact_batches = _search_query_batches(identity, _general_retail_queries(identity), per_query, on_event=on_event)',
)
replace_once(
    "src/product_intelligence/price_peru_coverage.py",
    '        alias_batches = _search_query_batches(alias_identity, _general_alias_queries(identity), per_query)',
    '        alias_batches = _search_query_batches(alias_identity, _general_alias_queries(identity), per_query, on_event=on_event)',
)

# P2.5 connect query diagnostics and capability memory to actual Price workflow.
replace_once(
    "src/product_intelligence/price_workflow.py",
    'from .price_peru_coverage import discover_additional_peru_pdps, discover_general_peru_retailers\nfrom .price_trace import PriceTrace\n',
    'from .price_peru_coverage import discover_additional_peru_pdps, discover_general_peru_retailers\nfrom .price_source_capabilities import SourceCapabilityRegistry, detect_platform\nfrom .price_trace import PriceTrace\n',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    'def _collect_web_offers(sources: list[str], identity: ProductIdentity, emit) -> list[PriceOffer]:',
    'def _collect_web_offers(sources: list[str], identity: ProductIdentity, emit, capabilities: SourceCapabilityRegistry | None = None) -> list[PriceOffer]:',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '            html, page_rows = _parse_page_with_dynamic_retry(url, identity, channel, emit)\n            rows.extend(_augment_page_rows(url, html, page_rows, identity, channel))\n            emit("page", url=url, channel=channel, status="parsed", offers=len(page_rows))',
    '            html, page_rows = _parse_page_with_dynamic_retry(url, identity, channel, emit)\n            augmented = _augment_page_rows(url, html, page_rows, identity, channel)\n            rows.extend(augmented)\n            if capabilities is not None:\n                method = next((row.source_method for row in augmented if row.source_method), None)\n                capabilities.observe(\n                    url,\n                    platform=detect_platform(url, html),\n                    discovery_method="price_discovery",\n                    extraction_method=method,\n                    price_capable=bool(augmented),\n                    stock_capable=any(row.stock is not None or bool(row.availability) for row in augmented),\n                    seller_capable=any(bool(row.seller_display_name or row.seller_legal_name) for row in augmented),\n                    success=any(_is_trusted_final_offer(row) for row in augmented),\n                )\n            emit("page", url=url, channel=channel, status="parsed", offers=len(page_rows))',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '    trace = PriceTrace()\n\n    def emit(event_type: str, **payload):',
    '    trace = PriceTrace()\n    capabilities = SourceCapabilityRegistry(Path(output_root) / "price_intelligence" / "source_capabilities.json")\n\n    def discovery_event(event: dict) -> None:\n        stage = str(event.get("stage") or "QUERY_EXECUTED")\n        payload = {k: v for k, v in event.items() if k != "stage"}\n        trace.record(stage, **payload)\n\n    def emit(event_type: str, **payload):',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '                limit=max(10, max_sources // 2),\n            )',
    '                limit=max(10, max_sources // 2),\n                on_event=discovery_event,\n            )',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '        offers.extend(_collect_web_offers(fresh_retail[:max_sources], identity, emit))',
    '        offers.extend(_collect_web_offers(fresh_retail[:max_sources], identity, emit, capabilities))',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '            marketplace_sources = discover_additional_peru_pdps(identity, limit_per_domain=max(4, min(10, max_sources // 4 or 4)))',
    '            marketplace_sources = discover_additional_peru_pdps(identity, limit_per_domain=max(4, min(10, max_sources // 4 or 4)), on_event=discovery_event)',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '                retail_sources = discover_general_peru_retailers(identity, limit=max(10, max_sources // 2))',
    '                retail_sources = discover_general_peru_retailers(identity, limit=max(10, max_sources // 2), on_event=discovery_event)',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '        offers.extend(_collect_web_offers(sources, identity, emit))',
    '        offers.extend(_collect_web_offers(sources, identity, emit, capabilities))',
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    '    save_channel_coverage(output_root, coverage)\n    emit("coverage", report=coverage)',
    '    save_channel_coverage(output_root, coverage)\n    capabilities.save()\n    emit("coverage", report=coverage)',
)

print("QUERY_CAPABILITIES_PATCH=APPLIED")
