from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import extract_page_offers
from product_intelligence.price_source_capabilities import detect_ecommerce_platform
from product_intelligence.web_fetch import fetch_page, fetch_static

# P7 forensic-only representatives. These URLs are NEVER injected into discovery or
# production source memory; they only reproduce the already-confirmed first-loss boundary.
CASES = {
    "Ripley-A": "https://simple.ripley.com.pe/disco-interno-solido-hdd-ssd-kingston-sa400s37-960gb-sata-pmp00001118622",
    "Ripley-B": "https://simple.ripley.com.pe/disco-duro-solido-kingston-960gb-ssd-a400-sata-6gbs-25-pmp00002109361",
    "Promart-A": "https://www.promart.pe/disco-duro-interno-solido-ssd-kingston-sa400s37-960gb-sata-1001168642/p",
    "Promart-B": "https://www.promart.pe/disco-solido-960-gb-kingston-ssdnow-a400---sa400s37-960g-1000215528/p",
    "PlazaVea": "https://www.plazavea.com.pe/disco-duro-ssd-960gb-a400-kingston-sa400s37-960g-101872434/p",
}
IDENTITY = ProductIdentity(mpn="SA400S37/960G", brand="Kingston")
MPN_COMPACT = re.sub(r"[^a-z0-9]+", "", IDENTITY.mpn.casefold())
PRICE_KEYS = {
    "price", "sellingprice", "saleprice", "listprice", "originalprice", "bestprice",
    "spotprice", "pricevalue", "offerprice", "lowprice", "highprice", "pricecurrency",
}
IDENTITY_KEYS = {"mpn", "partnumber", "part_number", "sku", "model", "name", "title", "productname"}


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def safe_scalar(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = str(value) if isinstance(value, str) else value
        if isinstance(text, str) and len(text) > 240:
            return text[:240] + "…"
        return text
    return type(value).__name__


def matching_objects(value: Any, *, max_hits: int = 18) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(node: Any, path: str) -> None:
        if len(hits) >= max_hits:
            return
        if isinstance(node, dict):
            identity_blob = " ".join(str(node.get(key) or "") for key in node if norm(key) in {norm(k) for k in IDENTITY_KEYS})
            all_blob = " ".join(str(v) for v in node.values() if isinstance(v, (str, int, float)))
            has_identity = MPN_COMPACT in norm(identity_blob) or MPN_COMPACT in norm(all_blob)
            price_fields = {str(k): safe_scalar(v) for k, v in node.items() if norm(k) in PRICE_KEYS}
            if has_identity and price_fields:
                identity_fields = {str(k): safe_scalar(v) for k, v in node.items() if norm(k) in {norm(x) for x in IDENTITY_KEYS}}
                hits.append({"path": path, "identity": identity_fields, "prices": price_fields})
            for key, child in node.items():
                walk(child, f"{path}.{key}")
        elif isinstance(node, list):
            for index, child in enumerate(node[:200]):
                walk(child, f"{path}[{index}]")

    walk(value, "$")
    return hits


def embedded_json_candidates(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "lxml")
    out: list[dict[str, Any]] = []
    for index, script in enumerate(soup.find_all("script")):
        raw = script.string or script.get_text() or ""
        if not raw or len(raw) > 2_000_000:
            continue
        script_id = str(script.get("id") or "")
        script_type = str(script.get("type") or "")
        if script_id == "__NEXT_DATA__" or "json" in script_type.casefold():
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            hits = matching_objects(obj)
            if hits:
                out.append({"index": index, "id": script_id, "type": script_type, "bytes": len(raw), "hits": hits})
    return out


def hydration_markers(html: str) -> list[str]:
    lower = (html or "").casefold()
    markers = [
        "__next_data__", "__nuxt__", "__apollo_state__", "__initial_state__", "__preloaded_state__",
        "vtex", "catalog_system", "commertialoffer", "commercialoffer", "sellingprice",
        "pricecurrency", "productprice", "pmp", "product_id",
    ]
    return [marker for marker in markers if marker in lower]


def summarize_fetch(label: str, result) -> dict[str, Any]:
    html = str(getattr(result, "html", "") or "")
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    json_rows = []
    for response in getattr(result, "json_responses", []) or []:
        data = response.get("data")
        hits = matching_objects(data)
        if hits:
            json_rows.append({
                "url": response.get("url"),
                "status": response.get("status"),
                "content_type": response.get("content_type"),
                "hits": hits,
            })
    return {
        "label": label,
        "requested_url": getattr(result, "url", None),
        "final_url": getattr(result, "final_url", None),
        "status_code": getattr(result, "status_code", None),
        "method": getattr(result, "method", None),
        "content_type": (getattr(result, "headers", {}) or {}).get("content-type"),
        "html_bytes": len(html.encode("utf-8", errors="ignore")),
        "title": title,
        "platform": detect_ecommerce_platform(str(getattr(result, "final_url", "") or ""), html),
        "mpn_exact_in_html": IDENTITY.mpn.casefold() in html.casefold(),
        "mpn_compact_in_html": MPN_COMPACT in norm(html),
        "hydration_markers": hydration_markers(html),
        "embedded_identity_price_json": embedded_json_candidates(html),
        "captured_json_count": len(getattr(result, "json_responses", []) or []),
        "captured_identity_price_json": json_rows,
        "network_resource_count": len(getattr(result, "network_resources", []) or []),
        "warnings": list(getattr(result, "warnings", []) or []),
    }


def main() -> int:
    report: dict[str, Any] = {"input_identity": IDENTITY.model_dump(), "cases": {}}
    for name, url in CASES.items():
        static = fetch_static(url, timeout=25)
        rendered = fetch_page(url, timeout=35, browser_fallback=True, prefer_browser=True, activate_lazy_media=False)
        current_rows = extract_page_offers(rendered.html, rendered.final_url or url, IDENTITY, channel=name.split("-")[0])
        report["cases"][name] = {
            "static": summarize_fetch("static", static),
            "rendered": summarize_fetch("rendered", rendered),
            "current_parser_offers": [row.to_dict() for row in current_rows],
        }
        print("P7_FORENSIC=", json.dumps({name: report["cases"][name]}, ensure_ascii=False, sort_keys=True))
    with open("p7_phase1_forensics.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
