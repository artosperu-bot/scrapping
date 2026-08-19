from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import extract_page_offers
from product_intelligence.web_fetch import fetch_page

IDENTITY = ProductIdentity(mpn="SA400S37/960G")
# QA-only aliases observed in the live accepted-offer set. Never used by production discovery.
URLS = [
    "https://compumarket.pe/producto/5500-disco-duro-solido-ssd-kingston-a400-960gb-sa400s37-960g-interno",
    "https://compumarket.pe/producto/5500-disco-duro-estado-solido-ssd-kingston-960gb-a400-sa400s37-960g-interno",
]


def _canonical_from_html(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    node = soup.select_one('link[rel="canonical"]')
    return str(node.get("href") or "").strip() if node else None


def _path_product_id(url: str) -> str | None:
    path = urlparse(url).path or ""
    match = re.search(r"/producto/(\d+)(?:-|/|$)", path, flags=re.IGNORECASE)
    return match.group(1) if match else None


def main() -> int:
    rows = []
    for url in URLS:
        try:
            fetched = fetch_page(url, timeout=25, browser_fallback=True, activate_lazy_media=False)
            html = str(getattr(fetched, "html", "") or "")
            final_url = str(getattr(fetched, "final_url", None) or url)
            offers = extract_page_offers(html, final_url, IDENTITY, channel="Compumarket")
            rows.append({
                "input_url": url,
                "final_url": final_url,
                "status_code": getattr(fetched, "status_code", None),
                "method": getattr(fetched, "method", None),
                "path_product_id": _path_product_id(final_url) or _path_product_id(url),
                "canonical_link": _canonical_from_html(html),
                "offers": [offer.to_dict() for offer in offers],
                "html_bytes": len(html.encode("utf-8", errors="ignore")),
            })
        except Exception as exc:
            rows.append({"input_url": url, "error": f"{type(exc).__name__}: {exc}"})

    product_ids = {row.get("path_product_id") for row in rows if row.get("path_product_id")}
    canonicals = {row.get("canonical_link") for row in rows if row.get("canonical_link")}
    final_urls = {row.get("final_url") for row in rows if row.get("final_url")}
    seller_keys = {
        (offer.get("seller_tax_id"), offer.get("seller_legal_name"), offer.get("seller_display_name"))
        for row in rows for offer in row.get("offers", [])
    }
    part_numbers = {offer.get("part_number") for row in rows for offer in row.get("offers", []) if offer.get("part_number")}
    prices = {(offer.get("currency"), offer.get("selling_price")) for row in rows for offer in row.get("offers", [])}

    same_publication = (
        len(rows) == 2
        and len(product_ids) == 1
        and "5500" in product_ids
        and len(seller_keys) <= 1
        and len(part_numbers) <= 1
        and len(prices) <= 1
    )
    report = {
        "input_identity": IDENTITY.model_dump(),
        "rows": rows,
        "product_ids": sorted(product_ids),
        "canonical_links": sorted(canonicals),
        "final_urls": sorted(final_urls),
        "seller_keys": [list(row) for row in sorted(seller_keys, key=str)],
        "part_numbers": sorted(part_numbers),
        "prices": [list(row) for row in sorted(prices, key=str)],
        "same_underlying_publication": same_publication,
        "dedupe_fix_required_if_both_survive": same_publication,
    }
    Path("p7_compumarket_dedupe_probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("P7_COMPUMARKET_DEDUPE=", json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
