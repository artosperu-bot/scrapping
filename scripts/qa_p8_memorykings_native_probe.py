from __future__ import annotations

import json
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import extract_page_offers
from product_intelligence.web_fetch import fetch_page


IDENTITY = ProductIdentity(mpn="SA400S37/960G")
BASE = "https://www.memorykings.pe"


def compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def aliases(identity: ProductIdentity) -> list[str]:
    raw = str(identity.mpn or "").strip()
    values = [raw, compact(raw), re.sub(r"[^A-Za-z0-9]+", "-", raw).strip("-")]
    return list(dict.fromkeys(value for value in values if value))


report = {"source": "memorykings.pe", "input": IDENTITY.model_dump(), "attempts": [], "accepted": []}
seen_pdps: set[str] = set()

for signal in aliases(IDENTITY):
    search_url = f"{BASE}/resultados/{quote(signal, safe='')}"
    attempt = {"signal": signal, "search_url": search_url, "status": None, "pdps": [], "offers": 0}
    try:
        fetched = fetch_page(search_url, timeout=20, browser_fallback=False, activate_lazy_media=False)
        attempt["status"] = getattr(fetched, "status_code", None)
        html = str(getattr(fetched, "html", "") or "")
        soup = BeautifulSoup(html, "html.parser")
        pdps = []
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href") or "").strip()
            if "/producto/" not in href.casefold():
                continue
            url = urljoin(BASE, href)
            if url not in seen_pdps:
                seen_pdps.add(url)
                pdps.append(url)
            if len(pdps) >= 12:
                break
        attempt["pdps"] = pdps
        for pdp in pdps:
            product = fetch_page(pdp, timeout=15, browser_fallback=False, activate_lazy_media=False)
            page_url = str(getattr(product, "final_url", None) or pdp)
            rows = extract_page_offers(str(getattr(product, "html", "") or ""), page_url, IDENTITY, channel="Memory Kings")
            exact = [row for row in rows if row.identity_match == "EXACT_MPN"]
            if exact:
                attempt["offers"] += len(exact)
                report["accepted"].extend({
                    "url": row.url,
                    "price": row.selling_price,
                    "currency": row.currency,
                    "identity_match": row.identity_match,
                    "source_method": row.source_method,
                } for row in exact)
                break
    except Exception as exc:
        attempt["error"] = f"{type(exc).__name__}: {exc}"
    report["attempts"].append(attempt)
    if report["accepted"]:
        break

print(json.dumps(report, ensure_ascii=False, indent=2))
if not report["accepted"]:
    raise SystemExit("MEMORYKINGS_NATIVE_DISCOVERY_NOT_PROVEN")
print("MEMORYKINGS_NATIVE_DISCOVERY=PROVEN")
