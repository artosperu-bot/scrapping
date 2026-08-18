from __future__ import annotations

import json
import os
import re
import threading
import traceback
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from unittest.mock import patch

from product_intelligence.models import ProductIdentity
from product_intelligence import (
    discovery,
    identity_bootstrap,
    price_adapters,
    price_discovery,
    price_identity,
    price_peru_coverage,
    price_workflow,
)

MPN = "SA400S37/960G"
OUTPUT_DIR = Path(os.environ.get("PRICE_BEFORE_OUTPUT", "qa_price_before_output"))
REPORT_PATH = OUTPUT_DIR / "before_sa400s37_960g.json"

# QA-only diagnostic mapping. These names/hints are NEVER passed into discovery.
# They are used only after the run to classify what the unchanged engine did.
BENCHMARK_SOURCES: dict[str, tuple[str, ...]] = {
    "Falabella": ("falabella",),
    "Ripley": ("ripley",),
    "Mercado Libre": ("mercadolibre",),
    "Coolbox": ("coolbox",),
    "Oechsle": ("oechsle",),
    "Sodimac": ("sodimac",),
    "Plaza Vea": ("plazavea",),
    "Promart": ("promart",),
    "Hiraoka": ("hiraoka",),
    "Supertec": ("supertec",),
    "Memory Kings": ("memorykings",),
    "Impacto": ("impacto",),
    "Baetech": ("baetech",),
    "NTPeru": ("ntperu",),
    "Gidat": ("gidat",),
    "Computer House": ("computerhouse",),
    "UnikStore": ("unikstore",),
    "Famtec": ("famtec",),
    "Compumarket": ("compumarket",),
    "Sercoplus": ("sercoplus",),
    "Corporación Luana": ("corporacionluana", "luana"),
    "Mesajil": ("mesajil",),
    "EAC": ("eac",),
    "Arteus": ("arteus",),
}


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _host(url: str | None) -> str:
    return (urlparse(str(url or "")).hostname or "").casefold().removeprefix("www.")


def _site_domain(query: str) -> str | None:
    match = re.search(r"\bsite:([^\s\"']+)", str(query or ""), re.I)
    if not match:
        return None
    return match.group(1).split("/", 1)[0].casefold().removeprefix("www.")


def _safe_identity(identity: ProductIdentity | None) -> dict[str, Any] | None:
    if identity is None:
        return None
    return identity.model_dump()


def _offer_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "to_dict"):
        return row.to_dict()
    return dict(row)


def _source_matches(name: str, *, url: str | None = None, channel: str | None = None, query: str | None = None) -> bool:
    hints = BENCHMARK_SOURCES[name]
    hay = " ".join((_host(url), _compact(channel), _compact(query)))
    compact_hay = _compact(hay)
    return any(_compact(hint) in compact_hay for hint in hints)


class Recorder:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.local = threading.local()
        self.sequence = 0
        self.events: list[dict[str, Any]] = []
        self.raw_search_seen: set[str] = set()
        self.admitted_urls: list[dict[str, Any]] = []
        self.candidate_offers: list[dict[str, Any]] = []
        self.final_offers: list[dict[str, Any]] = []
        self.bootstrap_results: list[dict[str, Any]] = []

    def add(self, kind: str, **payload: Any) -> dict[str, Any]:
        with self.lock:
            self.sequence += 1
            row = {"seq": self.sequence, "kind": kind, **payload}
            self.events.append(row)
            return row

    def set_stage(self, value: str | None) -> str | None:
        previous = getattr(self.local, "stage", None)
        self.local.stage = value
        return previous

    def restore_stage(self, previous: str | None) -> None:
        self.local.stage = previous

    def stage(self, default: str = "unknown") -> str:
        return str(getattr(self.local, "stage", None) or default)

    def set_context(self, *, url: str | None = None, channel: str | None = None) -> tuple[Any, Any]:
        previous = (getattr(self.local, "url", None), getattr(self.local, "channel", None))
        self.local.url = url
        self.local.channel = channel
        return previous

    def restore_context(self, previous: tuple[Any, Any]) -> None:
        self.local.url, self.local.channel = previous

    def context(self) -> tuple[str | None, str | None]:
        return getattr(self.local, "url", None), getattr(self.local, "channel", None)

    def record_query(self, stage: str, query: str, rows: list[Any], source: str) -> None:
        urls: list[str] = []
        for row in rows or []:
            if isinstance(row, (tuple, list)) and row:
                url = str(row[0] or "")
            elif hasattr(row, "url"):
                url = str(getattr(row, "url") or "")
            else:
                url = str(row or "")
            if url.startswith(("http://", "https://")):
                urls.append(url)
        with self.lock:
            new_urls = [url for url in urls if url not in self.raw_search_seen]
            self.raw_search_seen.update(urls)
        common = {
            "stage": stage,
            "query": query,
            "domain": _site_domain(query),
            "results": len(urls),
            "new_urls": len(new_urls),
            "urls": urls,
            "source": source,
        }
        self.add("QUERY_GENERATED", **common)
        self.add("SEARCH_EXECUTED", **common)

    def record_admitted(self, stage: str, urls: list[str]) -> None:
        for url in urls:
            item = {"stage": stage, "url": str(url)}
            self.admitted_urls.append(item)
            self.add("URL_DISCOVERED", **item)

    def record_offer(self, row: Any, phase: str, *, context_url: str | None = None, context_channel: str | None = None) -> None:
        payload = _offer_dict(row)
        payload["_phase"] = phase
        payload["_context_url"] = context_url
        payload["_context_channel"] = context_channel
        self.candidate_offers.append(payload)
        self.add(
            "PRICE_EXTRACTED",
            phase=phase,
            url=payload.get("url") or context_url,
            channel=payload.get("channel") or context_channel,
            price=payload.get("selling_price"),
            stock=payload.get("stock"),
            identity_match=payload.get("identity_match"),
            confidence=payload.get("confidence"),
        )
        if payload.get("stock") is not None:
            self.add(
                "STOCK_EXTRACTED",
                phase=phase,
                url=payload.get("url") or context_url,
                channel=payload.get("channel") or context_channel,
                stock=payload.get("stock"),
            )


rec = Recorder()


def _query_stage(query: str, default: str) -> str:
    domain = _site_domain(query)
    q = str(query or "").casefold()
    if domain:
        if domain in set(price_peru_coverage.PERU_RETAIL_HINT_DOMAINS):
            return "peru_retail"
        if domain in set(price_peru_coverage.PERU_MARKETPLACE_DOMAINS):
            return "peru_directed"
    if any(marker in q for marker in (" precio perú", " tienda perú", " comprar perú", '"s/" perú')):
        return "peru_retail"
    return default


def install_observers():
    patches = []

    original_discovery_provider = discovery._provider_search
    original_bootstrap_provider = identity_bootstrap._provider_search
    original_browser_search = identity_bootstrap.browser_search
    original_bootstrap_identity = identity_bootstrap.bootstrap_identity
    original_unknown_bootstrap = discovery._bootstrap_unknown_identity

    def observed_discovery_provider(query: str, timeout: int):
        rows = original_discovery_provider(query, timeout)
        rec.record_query(rec.stage("generic_web_discovery"), query, rows, "discovery._provider_search")
        return rows

    def observed_bootstrap_provider(query: str, timeout: int):
        rows = original_bootstrap_provider(query, timeout)
        rec.record_query("identity_bootstrap", query, rows, "identity_bootstrap._provider_search")
        return rows

    def observed_browser_search(*args, **kwargs):
        query = str(args[0] if args else kwargs.get("query") or kwargs.get("q") or "")
        rows = original_browser_search(*args, **kwargs)
        rec.record_query("identity_bootstrap_browser", query, rows or [], "identity_bootstrap.browser_search")
        return rows

    def observed_bootstrap_identity(identity, *args, **kwargs):
        rec.add("IDENTITY_BOOTSTRAP_STARTED", input=_safe_identity(identity))
        result = original_bootstrap_identity(identity, *args, **kwargs)
        payload = {
            "status": getattr(result, "status", None),
            "confidence": getattr(result, "confidence", None),
            "reason": getattr(result, "reason", None),
            "official_domain_hint": getattr(result, "official_domain_hint", None),
            "identity": _safe_identity(getattr(result, "identity", None)),
            "queries_executed": list(getattr(result, "queries_executed", []) or []),
            "candidate_urls": list(getattr(result, "candidate_urls", []) or []),
        }
        rec.bootstrap_results.append(payload)
        rec.add("IDENTITY_BOOTSTRAP_FINISHED", **payload)
        return result

    def observed_unknown_bootstrap(identity, timeout):
        before = _safe_identity(identity)
        effective, hint = original_unknown_bootstrap(identity, timeout)
        rec.add(
            "GENERIC_SEARCH_EFFECTIVE_IDENTITY",
            before=before,
            after=_safe_identity(effective),
            official_domain_hint=hint,
        )
        return effective, hint

    patches += [
        patch.object(discovery, "_provider_search", observed_discovery_provider),
        patch.object(identity_bootstrap, "_provider_search", observed_bootstrap_provider),
        patch.object(identity_bootstrap, "browser_search", observed_browser_search),
        patch.object(identity_bootstrap, "bootstrap_identity", observed_bootstrap_identity),
        patch.object(discovery, "_bootstrap_unknown_identity", observed_unknown_bootstrap),
    ]

    original_cov_search = price_peru_coverage.search_web_query
    original_pd_search_query = price_discovery.search_web_query
    original_pd_search_web = price_discovery.search_web

    def observed_cov_search(identity, query, *args, **kwargs):
        stage = _query_stage(query, "peru_coverage")
        previous = rec.set_stage(stage)
        try:
            urls = original_cov_search(identity, query, *args, **kwargs)
        finally:
            rec.restore_stage(previous)
        rec.add("RANKED_QUERY_RESULT", stage=stage, query=query, domain=_site_domain(query), results=len(urls), urls=list(urls))
        return urls

    def observed_pd_search_query(identity, query, *args, **kwargs):
        stage = _query_stage(query, "price_discovery_targeted")
        previous = rec.set_stage(stage)
        try:
            urls = original_pd_search_query(identity, query, *args, **kwargs)
        finally:
            rec.restore_stage(previous)
        rec.add("RANKED_QUERY_RESULT", stage=stage, query=query, domain=_site_domain(query), results=len(urls), urls=list(urls))
        return urls

    def observed_pd_search_web(identity, *args, **kwargs):
        previous = rec.set_stage("generic_web_discovery")
        try:
            rows = original_pd_search_web(identity, *args, **kwargs)
        finally:
            rec.restore_stage(previous)
        urls = [str(getattr(row, "url", "") or "") for row in rows]
        rec.add("GENERIC_DISCOVERY_RESULT", results=len(rows), urls=urls)
        return rows

    patches += [
        patch.object(price_peru_coverage, "search_web_query", observed_cov_search),
        patch.object(price_discovery, "search_web_query", observed_pd_search_query),
        patch.object(price_discovery, "search_web", observed_pd_search_web),
    ]

    original_directed = price_workflow.discover_additional_peru_pdps
    original_retail = price_workflow.discover_general_peru_retailers
    original_generic_sources = price_workflow.discover_price_sources
    original_merge_sources = price_workflow._merge_sources

    def observed_directed(identity, *args, **kwargs):
        urls = original_directed(identity, *args, **kwargs)
        rec.record_admitted("peru_directed", list(urls))
        return urls

    def observed_retail(identity, *args, **kwargs):
        urls = original_retail(identity, *args, **kwargs)
        rec.record_admitted("peru_retail", list(urls))
        return urls

    def observed_generic_sources(identity, *args, **kwargs):
        urls = original_generic_sources(identity, *args, **kwargs)
        rec.record_admitted("generic_peru", list(urls))
        return urls

    def observed_merge_sources(*groups, **kwargs):
        before = [str(url) for group in groups for url in group if str(url or "").strip()]
        merged = original_merge_sources(*groups, **kwargs)
        duplicate_occurrences = max(0, len(before) - len(set(before)))
        budget_dropped = max(0, len(set(before)) - len(merged))
        rec.add(
            "URL_DEDUPED",
            input_occurrences=len(before),
            input_unique=len(set(before)),
            output=len(merged),
            duplicate_occurrences=duplicate_occurrences,
            budget_dropped=budget_dropped,
            limit=kwargs.get("limit"),
        )
        return merged

    patches += [
        patch.object(price_workflow, "discover_additional_peru_pdps", observed_directed),
        patch.object(price_workflow, "discover_general_peru_retailers", observed_retail),
        patch.object(price_workflow, "discover_price_sources", observed_generic_sources),
        patch.object(price_workflow, "_merge_sources", observed_merge_sources),
    ]

    original_fetch_page = price_workflow.fetch_page

    def observed_fetch_page(url, *args, **kwargs):
        rec.add("FETCH_STARTED", url=str(url), channel=getattr(rec.local, "channel", None))
        try:
            result = original_fetch_page(url, *args, **kwargs)
        except Exception as exc:
            name = type(exc).__name__
            kind = "FETCH_TIMEOUT" if "timeout" in name.casefold() or "timeout" in str(exc).casefold() else "FETCH_BLOCKED" if any(x in str(exc) for x in ("401", "403", "429")) else "FETCH_FAILED"
            rec.add(kind, url=str(url), error=f"{name}: {exc}")
            raise
        status = getattr(result, "status_code", None)
        method = getattr(result, "method", None)
        final_url = str(getattr(result, "final_url", None) or url)
        if status in (401, 403, 429):
            rec.add("FETCH_BLOCKED", url=str(url), final_url=final_url, status_code=status, method=method)
        else:
            rec.add("FETCH_OK", url=str(url), final_url=final_url, status_code=status, method=method)
        return result

    patches.append(patch.object(price_workflow, "fetch_page", observed_fetch_page))

    original_score = price_identity.score_offer_identity

    def observed_score(identity, evidence):
        score, match, conflicts = original_score(identity, evidence)
        current_url, current_channel = rec.context()
        accepted = bool(score >= 0.70 and not conflicts)
        rec.add(
            "IDENTITY_ACCEPTED" if accepted else "IDENTITY_REJECTED",
            url=current_url,
            channel=current_channel,
            evidence=dict(evidence or {}),
            score=score,
            match=match,
            conflicts=list(conflicts or []),
        )
        return score, match, conflicts

    patches += [
        patch.object(price_discovery, "score_offer_identity", observed_score),
        patch.object(price_adapters, "score_offer_identity", observed_score),
    ]

    original_extract = price_workflow.extract_page_offers

    def observed_extract(html, url, identity, *args, **kwargs):
        channel = kwargs.get("channel")
        previous = rec.set_context(url=str(url), channel=channel)
        rec.add("PARSER_STARTED", url=str(url), channel=channel, parser="extract_page_offers")
        try:
            rows = original_extract(html, url, identity, *args, **kwargs)
        except Exception as exc:
            rec.add("PARSER_FAILED", url=str(url), channel=channel, error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            rec.restore_context(previous)
        kind = "PARSER_OK" if rows else "PARSER_ZERO_OFFERS"
        rec.add(kind, url=str(url), channel=channel, parser="extract_page_offers", offers=len(rows))
        for row in rows:
            rec.record_offer(row, "page_parser", context_url=str(url), context_channel=channel)
        return rows

    patches.append(patch.object(price_workflow, "extract_page_offers", observed_extract))

    original_vtex = price_workflow._try_vtex
    original_ml = price_workflow._try_mercadolibre
    original_shopify = price_workflow._try_shopify

    def observed_vtex(url, identity, channel, *args, **kwargs):
        query = price_workflow._query(identity)
        rec.add("DIRECT_SOURCE_STARTED", source="vtex", channel=channel, url=str(url), query=query)
        previous = rec.set_context(url=str(url), channel=channel)
        try:
            rows = original_vtex(url, identity, channel, *args, **kwargs)
        except Exception as exc:
            rec.add("DIRECT_SOURCE_FAILED", source="vtex", channel=channel, url=str(url), error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            rec.restore_context(previous)
        rec.add("DIRECT_SOURCE_FINISHED", source="vtex", channel=channel, url=str(url), query=query, offers=len(rows))
        for row in rows:
            rec.record_offer(row, "vtex", context_url=str(url), context_channel=channel)
        return rows

    def observed_ml(identity, *args, **kwargs):
        queries = list(price_workflow._mercadolibre_queries(identity))
        rec.add("DIRECT_SOURCE_STARTED", source="mercadolibre", channel="MercadoLibre", url="https://api.mercadolibre.com", queries=queries)
        previous = rec.set_context(url="https://api.mercadolibre.com", channel="MercadoLibre")
        try:
            rows = original_ml(identity, *args, **kwargs)
        except Exception as exc:
            rec.add("DIRECT_SOURCE_FAILED", source="mercadolibre", channel="MercadoLibre", url="https://api.mercadolibre.com", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            rec.restore_context(previous)
        rec.add("DIRECT_SOURCE_FINISHED", source="mercadolibre", channel="MercadoLibre", url="https://api.mercadolibre.com", queries=queries, offers=len(rows))
        for row in rows:
            rec.record_offer(row, "mercadolibre", context_url="https://api.mercadolibre.com", context_channel="MercadoLibre")
        return rows

    def observed_shopify(url, identity, channel, *args, **kwargs):
        previous = rec.set_context(url=str(url), channel=channel)
        rec.add("DIRECT_SOURCE_STARTED", source="shopify", channel=channel, url=str(url))
        try:
            rows = original_shopify(url, identity, channel, *args, **kwargs)
        except Exception as exc:
            rec.add("DIRECT_SOURCE_FAILED", source="shopify", channel=channel, url=str(url), error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            rec.restore_context(previous)
        rec.add("DIRECT_SOURCE_FINISHED", source="shopify", channel=channel, url=str(url), offers=len(rows))
        for row in rows:
            rec.record_offer(row, "shopify", context_url=str(url), context_channel=channel)
        return rows

    patches += [
        patch.object(price_workflow, "_try_vtex", observed_vtex),
        patch.object(price_workflow, "_try_mercadolibre", observed_ml),
        patch.object(price_workflow, "_try_shopify", observed_shopify),
    ]

    original_trust = price_workflow._is_trusted_final_offer
    original_dedupe = price_workflow.dedupe_offers
    original_outliers = price_workflow.filter_market_outliers

    def observed_trust(row):
        accepted = original_trust(row)
        payload = _offer_dict(row)
        rec.add(
            "OFFER_TRUST_ACCEPTED" if accepted else "OFFER_TRUST_REJECTED",
            url=payload.get("url"),
            channel=payload.get("channel"),
            seller=payload.get("seller_display_name"),
            price=payload.get("selling_price"),
            identity_match=payload.get("identity_match"),
            confidence=payload.get("confidence"),
            source_method=payload.get("source_method"),
        )
        if not accepted:
            rec.add(
                "PRICE_REJECTED",
                reason="final_trust_gate",
                url=payload.get("url"),
                channel=payload.get("channel"),
                price=payload.get("selling_price"),
            )
        return accepted

    def observed_dedupe(rows):
        materialized = list(rows)
        result = original_dedupe(materialized)
        rec.add("OFFER_DEDUPED", input=len(materialized), output=len(result), removed=max(0, len(materialized) - len(result)))
        return result

    def observed_outliers(rows):
        materialized = list(rows)
        valid, rejected = original_outliers(materialized)
        for row in rejected:
            payload = _offer_dict(row)
            rec.add("PRICE_REJECTED", reason="market_outlier", url=payload.get("url"), channel=payload.get("channel"), price=payload.get("selling_price"))
        rec.add("OUTLIER_FILTER", input=len(materialized), output=len(valid), rejected=len(rejected))
        return valid, rejected

    patches += [
        patch.object(price_workflow, "_is_trusted_final_offer", observed_trust),
        patch.object(price_workflow, "dedupe_offers", observed_dedupe),
        patch.object(price_workflow, "filter_market_outliers", observed_outliers),
    ]

    for item in patches:
        item.start()
    return patches


def _derive_query_rows(identity: ProductIdentity) -> list[dict[str, Any]]:
    query_events = [row for row in rec.events if row["kind"] == "SEARCH_EXECUTED"]
    ranked_events = [row for row in rec.events if row["kind"] == "RANKED_QUERY_RESULT"]
    ranked_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in ranked_events:
        ranked_by_key.setdefault((row.get("stage") or "", row.get("query") or ""), []).append(row)

    rows: list[dict[str, Any]] = []
    domain_execution: dict[str, list[dict[str, Any]]] = {}
    for event in query_events:
        domain = event.get("domain")
        if domain:
            domain_execution.setdefault(domain, []).append(event)

    break_domains: set[str] = set()
    for domain in price_peru_coverage.PERU_MARKETPLACE_DOMAINS:
        planned = price_peru_coverage._queries(identity, domain)
        executed = [row for row in domain_execution.get(domain, []) if row.get("stage") == "peru_directed"]
        if executed and any(int(row.get("results") or 0) > 0 for row in executed) and len(executed) < len(planned):
            break_domains.add(domain)

    seen_occurrence: Counter[tuple[str, str]] = Counter()
    for event in query_events:
        key = (event.get("stage") or "", event.get("query") or "")
        idx = seen_occurrence[key]
        seen_occurrence[key] += 1
        ranked_group = ranked_by_key.get(key, [])
        ranked = ranked_group[idx] if idx < len(ranked_group) else None
        rows.append({
            "query": event.get("query"),
            "stage": event.get("stage"),
            "domain": event.get("domain"),
            "raw_results": event.get("results"),
            "ranked_results": ranked.get("results") if ranked else None,
            "new_urls": event.get("new_urls"),
            "break_triggered": bool(event.get("domain") in break_domains and int(event.get("results") or 0) > 0),
            "source": event.get("source"),
        })
    return rows


def _identifier_contamination() -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for row in rec.candidate_offers:
        evidence = dict(row.get("evidence") or {})
        gtin = _compact(evidence.get("gtin"))
        sku = _compact(row.get("sku"))
        publication = _compact(row.get("publication_id"))
        collisions: list[str] = []
        if gtin and sku and gtin == sku:
            collisions.append("evidence.gtin == offer.sku")
        if gtin and publication and gtin == publication:
            collisions.append("evidence.gtin == publication_id")
        evidence_sku = _compact(evidence.get("sku"))
        if gtin and evidence_sku and gtin == evidence_sku:
            collisions.append("evidence.gtin == evidence.sku")
        if collisions:
            flags.append({
                "url": row.get("url"),
                "channel": row.get("channel"),
                "seller": row.get("seller_display_name"),
                "mpn": evidence.get("mpn"),
                "sku": row.get("sku"),
                "gtin": evidence.get("gtin"),
                "upc": evidence.get("upc"),
                "ean": evidence.get("ean"),
                "publication_id": row.get("publication_id"),
                "collisions": collisions,
            })
    return flags


def _coverage_by_source() -> list[dict[str, Any]]:
    query_events = [row for row in rec.events if row["kind"] == "SEARCH_EXECUTED"]
    direct_events = [row for row in rec.events if row["kind"].startswith("DIRECT_SOURCE_")]
    fetch_events = [row for row in rec.events if row["kind"].startswith("FETCH_")]
    parser_events = [row for row in rec.events if row["kind"].startswith("PARSER_")]
    identity_events = [row for row in rec.events if row["kind"] in {"IDENTITY_ACCEPTED", "IDENTITY_REJECTED"}]
    trust_events = [row for row in rec.events if row["kind"] in {"OFFER_TRUST_ACCEPTED", "OFFER_TRUST_REJECTED"}]
    price_rejected = [row for row in rec.events if row["kind"] == "PRICE_REJECTED"]

    admitted = [row["url"] for row in rec.admitted_urls]
    raw_urls = [url for event in query_events for url in event.get("urls", [])]
    all_discovered = list(dict.fromkeys(admitted + raw_urls))

    rows: list[dict[str, Any]] = []
    for name in BENCHMARK_SOURCES:
        source_queries = [
            row for row in query_events
            if row.get("domain") and _source_matches(name, query=f"site:{row.get('domain')}")
        ]
        source_direct = [
            row for row in direct_events
            if _source_matches(name, url=row.get("url"), channel=row.get("channel"))
        ]
        source_urls = [url for url in all_discovered if _source_matches(name, url=url)]
        source_fetch = [row for row in fetch_events if _source_matches(name, url=row.get("url")) or _source_matches(name, url=row.get("final_url"))]
        source_parser = [row for row in parser_events if _source_matches(name, url=row.get("url"), channel=row.get("channel"))]
        source_identity = [row for row in identity_events if _source_matches(name, url=row.get("url"), channel=row.get("channel"))]
        source_candidates = [
            row for row in rec.candidate_offers
            if _source_matches(name, url=row.get("url") or row.get("_context_url"), channel=row.get("channel") or row.get("_context_channel"))
        ]
        source_final = [
            row for row in rec.final_offers
            if _source_matches(name, url=row.get("url"), channel=row.get("channel"))
        ]
        source_trust = [row for row in trust_events if _source_matches(name, url=row.get("url"), channel=row.get("channel"))]
        source_price_rejected = [row for row in price_rejected if _source_matches(name, url=row.get("url"), channel=row.get("channel"))]

        searched = bool(source_queries or source_direct or source_urls)
        url_found = bool(source_urls or source_candidates or source_final)
        fetch_ok = any(row["kind"] == "FETCH_OK" for row in source_fetch) or any(row["kind"] == "DIRECT_SOURCE_FINISHED" for row in source_direct)
        fetch_failed = any(row["kind"] in {"FETCH_FAILED", "FETCH_BLOCKED", "FETCH_TIMEOUT"} for row in source_fetch) or any(row["kind"] == "DIRECT_SOURCE_FAILED" for row in source_direct)
        parsed = any(row["kind"] in {"PARSER_OK", "PARSER_ZERO_OFFERS"} for row in source_parser) or bool(source_candidates)
        parser_zero = any(row["kind"] == "PARSER_ZERO_OFFERS" for row in source_parser)
        identity_valid = any(row["kind"] == "IDENTITY_ACCEPTED" for row in source_identity) or bool(source_candidates)
        identity_rejected = any(row["kind"] == "IDENTITY_REJECTED" for row in source_identity)
        price_found = bool(source_candidates or source_final)
        stock_values = [row.get("stock") for row in source_candidates if row.get("stock") is not None]
        sellers = sorted({
            str(row.get("seller_display_name") or row.get("seller") or "").strip()
            for row in source_candidates + source_final
            if str(row.get("seller_display_name") or row.get("seller") or "").strip()
        })

        if source_final:
            unavailable = [
                row for row in source_final
                if row.get("stock") == 0 or "unavailable" in str(row.get("availability") or "").casefold() or "outofstock" in str(row.get("availability") or "").casefold()
            ]
            final_status = "OUT_OF_STOCK_FOUND" if len(unavailable) == len(source_final) else "OFFER_ACCEPTED"
            failure_stage = None
        elif source_price_rejected or any(row["kind"] == "OFFER_TRUST_REJECTED" for row in source_trust):
            final_status = "PRICE_REJECTED"
            failure_stage = "FINAL_QUALITY_GATE"
        elif identity_rejected and not identity_valid:
            final_status = "IDENTITY_REJECTED"
            failure_stage = "IDENTITY"
        elif parser_zero:
            final_status = "URL_PARSED_ZERO_OFFERS"
            failure_stage = "PARSER_EXTRACTION"
        elif fetch_failed and not fetch_ok:
            final_status = "URL_FETCH_FAILED"
            failure_stage = "FETCH_ACCESS"
        elif url_found:
            final_status = "URL_DISCOVERED"
            failure_stage = "POST_DISCOVERY"
        elif source_queries or source_direct:
            final_status = "QUERY_EXECUTED_NO_RESULT"
            failure_stage = "DISCOVERY"
        else:
            final_status = "NOT_SEARCHED"
            failure_stage = "DISCOVERY_NOT_TARGETED"

        rows.append({
            "source": name,
            "searched": searched,
            "specific_queries": len(source_queries),
            "url_found": url_found,
            "urls": source_urls,
            "fetched": bool(source_fetch or source_direct),
            "fetch_ok": fetch_ok,
            "parsed": parsed,
            "identity_valid": identity_valid,
            "price_found": price_found,
            "stock": stock_values or None,
            "seller": sellers or None,
            "candidate_offers": len(source_candidates),
            "final_offers": len(source_final),
            "final_status": final_status,
            "failure_stage": failure_stage,
        })
    return rows


def _marketplace_diagnostic() -> list[dict[str, Any]]:
    names = ("Mercado Libre", "Falabella", "Ripley", "Sodimac", "Plaza Vea")
    rows: list[dict[str, Any]] = []
    for name in names:
        urls = list(dict.fromkeys(
            row["url"] for row in rec.admitted_urls if _source_matches(name, url=row["url"])
        ))
        candidate = [
            row for row in rec.candidate_offers
            if _source_matches(name, url=row.get("url") or row.get("_context_url"), channel=row.get("channel") or row.get("_context_channel"))
        ]
        publications = sorted({str(row.get("publication_id")) for row in candidate if row.get("publication_id")})
        sellers = sorted({
            str(row.get("seller_display_name") or "").strip()
            for row in candidate if str(row.get("seller_display_name") or "").strip()
        })
        rows.append({
            "source": name,
            "catalog_or_product_pages_found": len(urls),
            "urls": urls,
            "publication_ids_found": len(publications),
            "publication_ids": publications,
            "sellers_discovered": len(sellers),
            "sellers": sellers,
            "offers_extracted_pre_final": len(candidate),
        })
    return rows


def _funnel() -> dict[str, Any]:
    q = [row for row in rec.events if row["kind"] == "SEARCH_EXECUTED"]
    fetch = [row for row in rec.events if row["kind"].startswith("FETCH_")]
    parsed = [row for row in rec.events if row["kind"] in {"PARSER_OK", "PARSER_ZERO_OFFERS"}]
    identity_ok = [row for row in rec.events if row["kind"] == "IDENTITY_ACCEPTED"]
    identity_bad = [row for row in rec.events if row["kind"] == "IDENTITY_REJECTED"]
    trust_bad = [row for row in rec.events if row["kind"] == "OFFER_TRUST_REJECTED"]
    price_bad = [row for row in rec.events if row["kind"] == "PRICE_REJECTED"]
    dedupe_calls = [row for row in rec.events if row["kind"] == "OFFER_DEDUPED"]
    final_dedupe = dedupe_calls[-1] if dedupe_calls else {"input": 0, "output": 0, "removed": 0}

    admitted_unique = {row["url"] for row in rec.admitted_urls}
    fetched_unique = {
        str(row.get("url"))
        for row in fetch
        if row["kind"] == "FETCH_STARTED" and row.get("url")
    }
    fetch_fail_urls = {
        str(row.get("url"))
        for row in fetch
        if row["kind"] in {"FETCH_FAILED", "FETCH_BLOCKED", "FETCH_TIMEOUT"} and row.get("url")
    }
    return {
        "queries": len(q),
        "search_results_raw": sum(int(row.get("results") or 0) for row in q),
        "unique_raw_search_urls": len(rec.raw_search_seen),
        "unique_urls_discovered_admitted": len(admitted_unique),
        "urls_fetched": len(fetched_unique),
        "fetch_failures": len(fetch_fail_urls),
        "parsed_pages": len(parsed),
        "zero_offer_pages": sum(1 for row in parsed if row["kind"] == "PARSER_ZERO_OFFERS"),
        "identity_accepted_evaluations": len(identity_ok),
        "identity_rejected_evaluations": len(identity_bad),
        "prices_extracted_candidate_offers": len(rec.candidate_offers),
        "prices_rejected_final_quality": len(price_bad),
        "offers_accepted": len(rec.final_offers),
        "duplicates_removed_final_dedupe": int(final_dedupe.get("removed") or 0),
        "final_dedupe_input": int(final_dedupe.get("input") or 0),
        "final_dedupe_output": int(final_dedupe.get("output") or 0),
    }


def build_report(identity: ProductIdentity, run_events: list[dict[str, Any]], run_error: str | None) -> dict[str, Any]:
    coverage = _coverage_by_source()
    query_rows = _derive_query_rows(identity)

    per_domain_behavior: list[dict[str, Any]] = []
    for domain in price_peru_coverage.PERU_MARKETPLACE_DOMAINS:
        planned = price_peru_coverage._queries(identity, domain)
        alias_planned = price_peru_coverage._alias_queries(identity, domain)
        executed = [row for row in query_rows if row.get("domain") == domain and row.get("stage") == "peru_directed"]
        per_domain_behavior.append({
            "domain": domain,
            "queries_planned_by_current_code": planned,
            "queries_executed": [row["query"] for row in executed],
            "results_by_query": [row.get("raw_results") for row in executed],
            "first_result_break_observed": any(row.get("break_triggered") for row in executed),
            "alias_queries_available_from_input": alias_planned,
            "aliases_attempted": any(row["query"] in alias_planned for row in executed),
            "brand_model_attempted": bool(identity.brand and identity.model and any(identity.model in row["query"] for row in executed)),
        })

    identity_effective_events = [row for row in rec.events if row["kind"] == "GENERIC_SEARCH_EFFECTIVE_IDENTITY"]
    report = {
        "benchmark": "BEFORE SA400S37/960G",
        "production_code_modified": 0,
        "qa_only_harness": True,
        "git": {
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_ref": os.environ.get("GITHUB_REF"),
            "github_head_ref": os.environ.get("GITHUB_HEAD_REF"),
            "github_base_ref": os.environ.get("GITHUB_BASE_REF"),
        },
        "input": {
            "constructor": 'ProductIdentity(mpn="SA400S37/960G")',
            "provided_fields": {"mpn": MPN},
        },
        "identity_before_discovery": {
            "brand": identity.brand or "UNKNOWN",
            "model": identity.model or "UNKNOWN",
            "mpn": identity.mpn or "UNKNOWN",
            "normalized_mpn": _compact(identity.mpn),
            "upc": identity.upc or "UNKNOWN",
            "ean": identity.ean or "UNKNOWN",
            "gtin": identity.gtin or "UNKNOWN",
            "price_workflow_primary_query": price_workflow._query(identity),
            "price_workflow_identity_object": _safe_identity(identity),
            "generic_search_effective_identities": identity_effective_events,
            "bootstrap_results": rec.bootstrap_results,
        },
        "queries_executed": query_rows,
        "per_domain_query_behavior": per_domain_behavior,
        "funnel": _funnel(),
        "coverage_by_source": coverage,
        "marketplace_behavior": _marketplace_diagnostic(),
        "accepted_offers": rec.final_offers,
        "identifier_contamination": _identifier_contamination(),
        "run_events": run_events,
        "trace_events": rec.events,
        "run_error": run_error,
    }
    return report


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    identity = ProductIdentity(mpn=MPN)
    run_events: list[dict[str, Any]] = []
    run_error: str | None = None
    observers = install_observers()
    try:
        offers = price_workflow.run_price_product(
            identity,
            OUTPUT_DIR / "engine_output",
            on_event=run_events.append,
            max_sources=48,
        )
        rec.final_offers = [_offer_dict(row) for row in offers]
        for row in rec.final_offers:
            rec.add(
                "OFFER_ACCEPTED",
                url=row.get("url"),
                channel=row.get("channel"),
                seller=row.get("seller_display_name"),
                price=row.get("selling_price"),
                stock=row.get("stock"),
            )
    except Exception as exc:
        run_error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        for observer in reversed(observers):
            observer.stop()

    report = build_report(identity, run_events, run_error)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("BEFORE_REPORT_PATH=", REPORT_PATH)
    print("INPUT=", json.dumps(report["input"], ensure_ascii=False))
    print("IDENTITY_BEFORE=", json.dumps(report["identity_before_discovery"], ensure_ascii=False))
    print("FUNNEL=", json.dumps(report["funnel"], ensure_ascii=False))
    print("COVERAGE=", json.dumps(report["coverage_by_source"], ensure_ascii=False))
    print("ACCEPTED_OFFERS=", json.dumps(report["accepted_offers"], ensure_ascii=False))
    print("IDENTIFIER_CONTAMINATION=", json.dumps(report["identifier_contamination"], ensure_ascii=False))
    print("RUN_ERROR=", run_error or "NONE")
    return 1 if run_error else 0


if __name__ == "__main__":
    raise SystemExit(main())