from __future__ import annotations

import json
import os
import time
from pathlib import Path

from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import extract_page_offers
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
    run_price_product,
)

IDENTITY = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
METHOD = os.environ.get("METHOD", "structured").strip().lower()
OUT = Path("price_method_benchmark") / METHOD
OUT.mkdir(parents=True, exist_ok=True)


def clean(rows):
    deduped = dedupe_offers(rows)
    trusted = [r for r in deduped if _is_trusted_final_offer(r)]
    valid, _ = filter_market_outliers(trusted)
    return valid


def crawl(urls):
    rows = []
    for url in urls:
        channel = _channel_from_url(url)
        try:
            html, page_rows = _parse_page_with_dynamic_retry(url, IDENTITY, channel, lambda *_a, **_k: None)
            rows.extend(page_rows)
            if "vtex" in html.lower() or "vteximg" in html.lower() or "/api/catalog_system/" in html.lower():
                rows.extend(_try_vtex(url, IDENTITY, channel))
            rows.extend(_try_shopify(url, IDENTITY, channel))
        except Exception as exc:
            print("SOURCE_ERROR", channel, url, type(exc).__name__, str(exc)[:180])
    return clean(rows)


started = time.perf_counter()
if METHOD == "structured":
    rows = []
    for channel, base_url in PERU_STRUCTURED_SOURCES:
        try:
            rows.extend(_try_vtex(base_url, IDENTITY, channel, timeout=6))
        except Exception as exc:
            print("STRUCTURED_ERROR", channel, type(exc).__name__, str(exc)[:180])
    try:
        rows.extend(_try_mercadolibre(IDENTITY, timeout=6))
    except Exception as exc:
        print("ML_ERROR", type(exc).__name__, str(exc)[:180])
    offers = clean(rows)
elif METHOD == "directed":
    urls = discover_additional_peru_pdps(IDENTITY, limit_per_domain=8)
    print("DISCOVERED_URLS", len(urls))
    offers = crawl(urls[:24])
elif METHOD == "retail":
    urls = discover_general_peru_retailers(IDENTITY, limit=24)
    print("DISCOVERED_URLS", len(urls))
    offers = crawl(urls[:24])
elif METHOD == "full":
    offers = run_price_product(IDENTITY, OUT, max_sources=24)
else:
    raise SystemExit(f"unknown METHOD={METHOD}")

elapsed = round(time.perf_counter() - started, 2)
channels = sorted({o.channel for o in offers})
result = {
    "method": METHOD,
    "offers": len(offers),
    "channels": channels,
    "elapsed_seconds": elapsed,
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
