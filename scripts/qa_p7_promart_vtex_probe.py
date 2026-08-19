from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests

from product_intelligence.models import ProductIdentity
from product_intelligence.price_adapters import parse_vtex_payload
from product_intelligence.price_queries import build_price_query_plan


IDENTITY = ProductIdentity(mpn="SA400S37/960G")
ORIGIN = "https://www.promart.pe"


def main() -> int:
    plan = [row for row in build_price_query_plan(IDENTITY, limit=12) if str(row.signal_type).startswith("MPN_")][:3]
    report = {"input_identity": IDENTITY.model_dump(), "origin": ORIGIN, "queries": []}
    accepted = []
    for row in plan:
        endpoint = f"{ORIGIN}/api/catalog_system/pub/products/search?ft={quote_plus(row.query)}&_from=0&_to=49"
        started = time.perf_counter()
        try:
            response = requests.get(endpoint, timeout=20, headers={"Accept": "application/json", "User-Agent": "ProductIntelligence/0.10"})
            elapsed = round(time.perf_counter() - started, 3)
            try:
                payload = response.json()
            except Exception:
                payload = None
            raw_count = len(payload) if isinstance(payload, list) else 0
            offers = parse_vtex_payload(payload, IDENTITY, channel="Promart", source_url=ORIGIN) if isinstance(payload, (list, dict)) else []
            products = []
            if isinstance(payload, list):
                for product in payload[:10]:
                    if not isinstance(product, dict):
                        continue
                    products.append({
                        "productId": product.get("productId"),
                        "productName": product.get("productName"),
                        "link": product.get("link"),
                        "linkText": product.get("linkText"),
                        "items": [
                            {
                                "itemId": item.get("itemId"),
                                "name": item.get("name"),
                                "nameComplete": item.get("nameComplete"),
                                "ean": item.get("ean"),
                                "referenceId": item.get("referenceId"),
                                "sellers": [
                                    {
                                        "sellerId": seller.get("sellerId"),
                                        "sellerName": seller.get("sellerName"),
                                        "commertialOffer": seller.get("commertialOffer"),
                                    }
                                    for seller in (item.get("sellers") or [])[:10]
                                    if isinstance(seller, dict)
                                ],
                            }
                            for item in (product.get("items") or [])[:10]
                            if isinstance(item, dict)
                        ],
                    })
            entry = {
                "query": row.query,
                "signal_type": row.signal_type,
                "endpoint": endpoint,
                "http_status": response.status_code,
                "runtime_seconds": elapsed,
                "raw_products": raw_count,
                "products": products,
                "accepted_offers": [offer.to_dict() for offer in offers],
            }
            report["queries"].append(entry)
            accepted.extend(offers)
            print("P7_PROMART_VTEX=", json.dumps(entry, ensure_ascii=False, sort_keys=True))
        except Exception as exc:
            entry = {
                "query": row.query,
                "signal_type": row.signal_type,
                "endpoint": endpoint,
                "error": f"{type(exc).__name__}: {exc}",
            }
            report["queries"].append(entry)
            print("P7_PROMART_VTEX=", json.dumps(entry, ensure_ascii=False, sort_keys=True))

    report["summary"] = {
        "queries": len(report["queries"]),
        "queries_with_products": sum(1 for row in report["queries"] if row.get("raw_products", 0) > 0),
        "accepted_offers": len(accepted),
        "unique_offer_urls": sorted({offer.url for offer in accepted if offer.url}),
    }
    Path("p7_promart_vtex_probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("P7_PROMART_VTEX_SUMMARY=", json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
