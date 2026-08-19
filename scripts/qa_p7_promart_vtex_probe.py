from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests

from product_intelligence.models import ProductIdentity
from product_intelligence.price_adapters import parse_vtex_payload
from product_intelligence.price_queries import build_price_query_plan


IDENTITY = ProductIdentity(mpn="SA400S37/960G")
ORIGIN = "https://www.promart.pe"
EXPECTED = re.sub(r"[^a-z0-9]+", "", IDENTITY.mpn.casefold())


def _norm(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _identity_paths(value, path="$", *, max_hits=30):
    hits = []
    def walk(node, current):
        if len(hits) >= max_hits:
            return
        if isinstance(node, dict):
            for key, child in node.items():
                next_path = f"{current}.{key}"
                if isinstance(child, (str, int, float, bool)):
                    normalized = _norm(child)
                    if EXPECTED and EXPECTED in normalized:
                        hits.append({"path": next_path, "value": str(child)[:500]})
                else:
                    walk(child, next_path)
        elif isinstance(node, list):
            for index, child in enumerate(node[:200]):
                walk(child, f"{current}[{index}]")
    walk(value, path)
    return hits


def _product_forensics(product):
    if not isinstance(product, dict):
        return {}
    name = str(product.get("productName") or "")
    if "kingston" not in name.casefold() or "960" not in name.casefold():
        return {}
    scalar_fields = {
        key: value for key, value in product.items()
        if isinstance(value, (str, int, float, bool, type(None)))
    }
    structured_fields = {}
    for key in ("allSpecifications", "allSpecificationsGroups", "categories", "categoryId", "description", "items", "Modelo", "Model", "MPN", "Part Number", "productReference", "productReferenceCode"):
        if key in product:
            value = product.get(key)
            if key == "items" and isinstance(value, list):
                structured_fields[key] = [
                    {
                        k: item.get(k)
                        for k in ("itemId", "name", "nameComplete", "complementName", "ean", "referenceId", "variations")
                        if k in item
                    }
                    for item in value[:10] if isinstance(item, dict)
                ]
            else:
                structured_fields[key] = value
    return {
        "productId": product.get("productId"),
        "productName": name,
        "keys": sorted(product.keys()),
        "scalar_fields": scalar_fields,
        "selected_structured_fields": structured_fields,
        "exact_mpn_paths": _identity_paths(product),
    }


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
            forensic_products = []
            if isinstance(payload, list):
                for product in payload[:50]:
                    if not isinstance(product, dict):
                        continue
                    products.append({
                        "productId": product.get("productId"),
                        "productName": product.get("productName"),
                        "brand": product.get("brand"),
                        "link": product.get("link"),
                        "linkText": product.get("linkText"),
                        "productReference": product.get("productReference"),
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
                    forensic = _product_forensics(product)
                    if forensic:
                        forensic_products.append(forensic)
            entry = {
                "query": row.query,
                "signal_type": row.signal_type,
                "endpoint": endpoint,
                "http_status": response.status_code,
                "runtime_seconds": elapsed,
                "raw_products": raw_count,
                "products": products,
                "forensic_products": forensic_products,
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
