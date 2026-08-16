from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import discover_price_sources, extract_page_offers
from product_intelligence.price_identity import dedupe_offers, filter_market_outliers
from product_intelligence.price_peru_coverage import discover_additional_peru_pdps, discover_general_peru_retailers
from product_intelligence.price_workflow import (
    BROWSER_PRICE_CHANNELS,
    PERU_STRUCTURED_SOURCES,
    _channel_from_url,
    _is_trusted_final_offer,
    _parse_page_with_dynamic_retry,
    _try_mercadolibre,
    _try_shopify,
    _try_vtex,
)
from product_intelligence.web_fetch import fetch_page

IDENTITY = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
METHOD = os.environ.get("METHOD", "two_phase").strip().lower()
OUT = Path("price_method_benchmark") / METHOD
OUT.mkdir(parents=True, exist_ok=True)


def clean(rows):
    deduped = dedupe_offers(rows)
    trusted = [r for r in deduped if _is_trusted_final_offer(r)]
    valid, _ = filter_market_outliers(trusted)
    return valid


def merge_urls(*groups, limit=None):
    merged, seen = [], set()
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


def structured_rows():
    rows = []

    def vtex_job(pair):
        channel, base_url = pair
        try:
            return _try_vtex(base_url, IDENTITY, channel, timeout=6)
        except Exception as exc:
            print("STRUCTURED_ERROR", channel, type(exc).__name__, str(exc)[:180])
            return []

    def ml_job():
        try:
            return _try_mercadolibre(IDENTITY, timeout=6)
        except Exception as exc:
            print("ML_ERROR", type(exc).__name__, str(exc)[:180])
            return []

    with ThreadPoolExecutor(max_workers=len(PERU_STRUCTURED_SOURCES) + 1) as pool:
        futures = [pool.submit(vtex_job, pair) for pair in PERU_STRUCTURED_SOURCES]
        futures.append(pool.submit(ml_job))
        for future in as_completed(futures):
            rows.extend(future.result())
    return clean(rows)


def static_one(url):
    channel = _channel_from_url(url)
    rows = []
    try:
        fetched = fetch_page(url, timeout=8, browser_fallback=False, activate_lazy_media=False)
        final_url = str(getattr(fetched, "final_url", None) or url)
        html = str(getattr(fetched, "html", "") or "")
        rows.extend(extract_page_offers(html, final_url, IDENTITY, channel=channel))
        lower = html.lower()
        if "vtex" in lower or "vteximg" in lower or "/api/catalog_system/" in lower:
            rows.extend(_try_vtex(final_url, IDENTITY, channel, timeout=6))
        rows.extend(_try_shopify(final_url, IDENTITY, channel, timeout=6))
        return url, clean(rows), int(getattr(fetched, "status_code", 0) or 0)
    except Exception as exc:
        print("STATIC_ERROR", channel, url, type(exc).__name__, str(exc)[:180])
        return url, [], 0


def static_parallel(urls, workers=12):
    rows, unresolved = [], []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(urls) or 1))) as pool:
        futures = {pool.submit(static_one, url): url for url in urls}
        for future in as_completed(futures):
            url, found, status = future.result()
            rows.extend(found)
            if not found:
                unresolved.append((url, status))
    return clean(rows), unresolved


def browser_fallback(unresolved, max_urls=18):
    rows = []
    prioritized = sorted(
        unresolved,
        key=lambda item: (
            0 if _channel_from_url(item[0]) in BROWSER_PRICE_CHANNELS else 1,
            0 if item[1] in {401, 403, 429} else 1,
        ),
    )[:max_urls]
    print("BROWSER_FALLBACK_URLS", len(prioritized))
    for url, _status in prioritized:
        channel = _channel_from_url(url)
        try:
            html, page_rows = _parse_page_with_dynamic_retry(url, IDENTITY, channel, lambda *_a, **_k: None)
            rows.extend(page_rows)
            lower = html.lower()
            if "vtex" in lower or "vteximg" in lower or "/api/catalog_system/" in lower:
                rows.extend(_try_vtex(url, IDENTITY, channel, timeout=6))
            rows.extend(_try_shopify(url, IDENTITY, channel, timeout=6))
        except Exception as exc:
            print("BROWSER_ERROR", channel, url, type(exc).__name__, str(exc)[:180])
    return clean(rows)


def discover_all():
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="price-discovery") as pool:
        f_retail = pool.submit(discover_general_peru_retailers, IDENTITY, limit=60)
        f_directed = pool.submit(discover_additional_peru_pdps, IDENTITY, limit_per_domain=8)
        f_generic = pool.submit(discover_price_sources, IDENTITY, 48)
        retail = f_retail.result()
        directed = f_directed.result()
        generic = f_generic.result()
    print("DISCOVERY_COUNTS", json.dumps({"retail": len(retail), "directed": len(directed), "generic": len(generic)}))
    return merge_urls(retail, directed, generic, limit=96)


if METHOD != "two_phase":
    raise SystemExit(f"unknown METHOD={METHOD}")

started = time.perf_counter()
with ThreadPoolExecutor(max_workers=2) as pool:
    api_future = pool.submit(structured_rows)
    discover_future = pool.submit(discover_all)
    api_rows = api_future.result()
    urls = discover_future.result()

print("MERGED_URLS", len(urls))
static_rows, unresolved = static_parallel(urls, workers=12)
print("STATIC_OFFERS", len(static_rows), "UNRESOLVED", len(unresolved))
browser_rows = browser_fallback(unresolved, max_urls=18)
offers = clean(api_rows + static_rows + browser_rows)

elapsed = round(time.perf_counter() - started, 2)
result = {
    "method": METHOD,
    "offers": len(offers),
    "channels": sorted({o.channel for o in offers}),
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
