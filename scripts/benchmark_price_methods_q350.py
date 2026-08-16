from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import extract_page_offers
from product_intelligence.price_identity import dedupe_offers, filter_market_outliers
from product_intelligence.price_peru_coverage import discover_general_peru_retailers
from product_intelligence.price_workflow import (
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
METHOD = os.environ.get("METHOD", "learned").strip().lower()
OUT = Path("price_method_benchmark") / METHOD
OUT.mkdir(parents=True, exist_ok=True)

# Benchmark seed only: these URLs are the union of EXACT_MPN/BRAND_MODEL offers
# discovered by previous runs of this scraper. Production must persist this data,
# never hardcode product/store URLs.
LEARNED_URLS = [
    "https://www.falabella.com.pe/falabella-pe/product/121511774/Audifonos-Gamer-JBL-Quantum-350-Wireless-Negro-JBLQ350WLBLKAM/121511775",
    "https://www.sodimac.com.pe/sodimac-pe/articulo/121511774/Audifonos-Gamer-JBL-Quantum-350-Wireless-Negro-JBLQ350WLBLKAM/121511775",
    "https://www.memorykings.pe/producto/347928/auricular-jbl-quantum-350-wireless-black",
    "https://www.panacompu.com/peru/en/product-information/jbl-quantum-350-headset-stereo-over-ear-headband-wireless-bluetooth-20-hz-20-khz-black",
    "https://arteus.pe/products/jbl-jblq350wlblkam-quantum-350-wireless-auriculares-inalambricos-para-gaming-en-pc-con-microfono-de-asta-desmontable?variant=43894580773081",
    "https://www.perudataconsult.net/products/audifono-c-microfono-jbl-quantum-q350-gaming-negro-jblq350wlblkam?variant=40181600419953",
    "https://baetech.pe/products/jbl-quantum-350-wireless-auriculares-inalambricos-para-gaming-en-pc-con-microfono-de-asta-desmontable-jblq350wlblkam?variant=44937416704278",
    "https://www.infiniti.com.pe/shop/jblq350wlblkam-audifonos-jbl-herman-quantum-350-wireless-black-jblq350wlblkam-hasta-22-horas-de-bateria-compatible-android-ios-adaptador-de-audio-usb-filtro-antiviento-de-espuma-para-microfono-color-negro-9016#attr=11397,15527",
    "https://estuyo.pe/producto/jbl-audifono-quantum-350-wireless-microfono-desmontable-negro/",
    "https://www.plazavea.com.pe/audifonos-over-ear-jbl-jblq350wlblkam-negro/p",
]


def clean(rows):
    deduped = dedupe_offers(rows)
    trusted = [r for r in deduped if _is_trusted_final_offer(r)]
    valid, _ = filter_market_outliers(trusted)
    return valid


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
        return clean(rows)
    except Exception as exc:
        print("STATIC_ERROR", channel, url, type(exc).__name__, str(exc)[:180])
        return []


def refresh_urls(urls):
    rows, unresolved = [], []
    with ThreadPoolExecutor(max_workers=min(10, max(1, len(urls)))) as pool:
        futures = {pool.submit(static_one, url): url for url in urls}
        for future in as_completed(futures):
            found = future.result()
            rows.extend(found)
            if not found:
                unresolved.append(futures[future])
    print("STATIC_VALID", len(clean(rows)), "UNRESOLVED", len(unresolved))
    # Browser is a controlled fallback only for learned URLs that failed static refresh.
    for url in unresolved:
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


def structured_rows():
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
    return clean(rows)


if METHOD != "learned":
    raise SystemExit(f"unknown METHOD={METHOD}")

started = time.perf_counter()
with ThreadPoolExecutor(max_workers=3) as pool:
    learned_future = pool.submit(refresh_urls, LEARNED_URLS)
    discovery_future = pool.submit(discover_general_peru_retailers, IDENTITY, limit=32)
    api_future = pool.submit(structured_rows)
    learned_rows = learned_future.result()
    fresh_urls = discovery_future.result()
    api_rows = api_future.result()

learned_set = set(LEARNED_URLS)
new_urls = [url for url in fresh_urls if url not in learned_set]
print("LEARNED_ROWS", len(learned_rows), "FRESH_DISCOVERY", len(fresh_urls), "NEW_URLS", len(new_urls))
new_rows = refresh_urls(new_urls[:24]) if new_urls else []
offers = clean(learned_rows + new_rows + api_rows)

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
