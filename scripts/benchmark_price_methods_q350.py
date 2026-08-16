from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import discover_price_sources
from product_intelligence.price_identity import dedupe_offers, filter_market_outliers
from product_intelligence.price_peru_coverage import discover_additional_peru_pdps, discover_general_peru_retailers
from product_intelligence.price_workflow import (
    PERU_STRUCTURED_SOURCES,
    _channel_from_url,
    _is_trusted_final_offer,
    _parse_page_with_dynamic_retry,
    _try_mercadolibre,
    _try_shopify,
    _try_vtex,
)

IDENTITY = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
METHOD = os.environ.get("METHOD", "retail48").strip().lower()
OUT = Path("price_method_benchmark") / METHOD
OUT.mkdir(parents=True, exist_ok=True)


def clean(rows):
    deduped = dedupe_offers(rows)
    trusted = [r for r in deduped if _is_trusted_final_offer(r)]
    valid, _ = filter_market_outliers(trusted)
    return valid


def merge_urls(*groups, limit: int | None = None):
    merged = []
    seen = set()
    max_len = max((len(group) for group in groups), default=0)
    for index in range(max_len):
        for group in groups:
            if index >= len(group):
                continue
            url = str(group[index] or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(url)
            if limit is not None and len(merged) >= limit:
                return merged
    return merged


def crawl_one(url):
    rows = []
    channel = _channel_from_url(url)
    try:
        html, page_rows = _parse_page_with_dynamic_retry(url, IDENTITY, channel, lambda *_a, **_k: None)
        rows.extend(page_rows)
        lower = html.lower()
        if "vtex" in lower or "vteximg" in lower or "/api/catalog_system/" in lower:
            rows.extend(_try_vtex(url, IDENTITY, channel, timeout=6))
        rows.extend(_try_shopify(url, IDENTITY, channel, timeout=6))
    except Exception as exc:
        print("SOURCE_ERROR", channel, url, type(exc).__name__, str(exc)[:180])
    return rows


def crawl_parallel(urls, workers=10):
    rows = []
    unique = merge_urls(urls)
    if not unique:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(unique))), thread_name_prefix="price-crawl") as pool:
        futures = {pool.submit(crawl_one, url): url for url in unique}
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except Exception as exc:
                print("CRAWL_ERROR", futures[future], type(exc).__name__, str(exc)[:180])
    return clean(rows)


def structured_rows():
    rows = []
    def vtex_job(pair):
        channel, base_url = pair
        try:
            return _try_vtex(base_url, IDENTITY, channel, timeout=6)
        except Exception as exc:
            print("STRUCTURED_ERROR", channel, type(exc).__name__, str(exc)[:180])
            return []

    with ThreadPoolExecutor(max_workers=len(PERU_STRUCTURED_SOURCES) + 1, thread_name_prefix="price-api") as pool:
        futures = [pool.submit(vtex_job, pair) for pair in PERU_STRUCTURED_SOURCES]
        futures.append(pool.submit(_mercadolibre_rows))
        for future in as_completed(futures):
            rows.extend(future.result())
    return clean(rows)


def _mercadolibre_rows():
    try:
        return _try_mercadolibre(IDENTITY, timeout=6)
    except Exception as exc:
        print("ML_ERROR", type(exc).__name__, str(exc)[:180])
        return []


def discover_parallel(*, retail_limit, directed_per_domain, generic_limit, include_generic):
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="price-discovery") as pool:
        retail_future = pool.submit(discover_general_peru_retailers, IDENTITY, limit=retail_limit)
        directed_future = pool.submit(discover_additional_peru_pdps, IDENTITY, limit_per_domain=directed_per_domain)
        generic_future = pool.submit(discover_price_sources, IDENTITY, generic_limit) if include_generic else None
        retail = retail_future.result()
        directed = directed_future.result()
        generic = generic_future.result() if generic_future else []
    print("DISCOVERY_COUNTS", json.dumps({"retail": len(retail), "directed": len(directed), "generic": len(generic)}))
    return retail, directed, generic


started = time.perf_counter()
if METHOD == "retail48":
    urls = discover_general_peru_retailers(IDENTITY, limit=48)
    print("DISCOVERED_URLS", len(urls))
    offers = crawl_parallel(urls, workers=10)
elif METHOD == "hybrid":
    retail, directed, _ = discover_parallel(
        retail_limit=48,
        directed_per_domain=5,
        generic_limit=0,
        include_generic=False,
    )
    urls = merge_urls(retail, directed, limit=72)
    print("MERGED_URLS", len(urls))
    with ThreadPoolExecutor(max_workers=2) as pool:
        api_future = pool.submit(structured_rows)
        crawl_future = pool.submit(crawl_parallel, urls, 10)
        offers = clean(api_future.result() + crawl_future.result())
elif METHOD == "exhaustive":
    retail, directed, generic = discover_parallel(
        retail_limit=80,
        directed_per_domain=10,
        generic_limit=64,
        include_generic=True,
    )
    urls = merge_urls(retail, directed, generic, limit=120)
    print("MERGED_URLS", len(urls))
    with ThreadPoolExecutor(max_workers=2) as pool:
        api_future = pool.submit(structured_rows)
        crawl_future = pool.submit(crawl_parallel, urls, 12)
        offers = clean(api_future.result() + crawl_future.result())
else:
    raise SystemExit(f"unknown METHOD={METHOD}")

elapsed = round(time.perf_counter() - started, 2)
channels = sorted({o.channel for o in offers})
result = {
    "method": METHOD,
    "offers": len(offers),
    "channels": channels,
    "elapsed_seconds": elapsed,
    "exact_identity_offers": sum(1 for o in offers if str(o.identity_match or "").startswith("EXACT_")),
    "prices": [
        {
            "channel": o.channel,
            "seller": o.seller_display_name,
            "price": o.selling_price,
            "currency": o.currency,
            "identity_match": o.identity_match,
            "method": o.source_method,
            "stock": o.stock,
            "availability": o.availability,
            "url": o.url,
        }
        for o in offers
    ],
}
print("PRICE_METHOD_RESULT=" + json.dumps(result, ensure_ascii=False))
(OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
