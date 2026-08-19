from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlparse

from product_intelligence.discovery import search_web_query
from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import extract_page_offers
from product_intelligence.price_queries import build_price_query_plan
from product_intelligence.price_source_capabilities import detect_ecommerce_platform
from product_intelligence.web_fetch import fetch_page

IDENTITY = ProductIdentity(mpn="SA400S37/960G", brand="Kingston")
SOURCES = {
    "Memory Kings": ("memorykings.pe", "https://www.memorykings.pe/producto/322249/unidad-ssd-2-5-sata-960gb-kingston-a400"),
    "Supertec": ("supertec.com.pe", "https://supertec.com.pe/detalle-productos/520/img-apps/productos/inicio"),
    "Impacto": ("impacto.com.pe", "https://www.impacto.com.pe/producto/unidad-de-almacenamiento-ssd-sata-2-5-kingston-960gb-a400-sa400s37960g-500mbs"),
}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def main() -> int:
    signals = [row for row in build_price_query_plan(IDENTITY, limit=12) if str(row.signal_type).startswith("MPN_")][:3]
    report = {"input_identity": IDENTITY.model_dump(), "global_queries": [], "sources": {}}
    for query in (
        '"Kingston" "SA400S37/960G" site:.pe',
        '"Kingston" "SA400S37/960G" site:.com.pe',
    ):
        started = time.perf_counter()
        urls = search_web_query(IDENTITY, query, limit=12, timeout=15)
        report["global_queries"].append({
            "query": query,
            "signal_type": "BRAND_MPN_PERU_SCOPE",
            "valid_results": len(urls),
            "new_domains": sorted({_host(url) for url in urls if _host(url)}),
            "urls": urls,
            "runtime_seconds": round(time.perf_counter() - started, 3),
        })
    print("P7_PHASE3_GLOBAL=", json.dumps(report["global_queries"], ensure_ascii=False, sort_keys=True))

    for label, (domain, oracle_url) in SOURCES.items():
        queries = []
        admitted = []
        for row in signals:
            query = f'"{row.query}" site:{domain}'
            started = time.perf_counter()
            try:
                urls = search_web_query(IDENTITY, query, limit=7, timeout=15, required_domain=domain)
                error = None
            except Exception as exc:
                urls = []
                error = f"{type(exc).__name__}: {exc}"
            queries.append({"query": query, "signal_type": row.signal_type, "valid_urls": urls, "valid_results": len(urls), "oracle_returned": oracle_url in urls, "runtime_seconds": round(time.perf_counter() - started, 3), "error": error})
            for url in urls:
                if url not in admitted:
                    admitted.append(url)
        try:
            fetched = fetch_page(oracle_url, timeout=30, browser_fallback=True, activate_lazy_media=False)
            html = str(getattr(fetched, "html", "") or "")
            final_url = str(getattr(fetched, "final_url", None) or oracle_url)
            offers = extract_page_offers(html, final_url, IDENTITY, channel=label)
            direct = {"status_code": getattr(fetched, "status_code", None), "method": getattr(fetched, "method", None), "final_url": final_url, "platform": detect_ecommerce_platform(final_url, html), "html_bytes": len(html.encode("utf-8", errors="ignore")), "exact_mpn_in_html": IDENTITY.mpn.casefold() in html.casefold(), "offers": [offer.to_dict() for offer in offers]}
        except Exception as exc:
            direct = {"error": f"{type(exc).__name__}: {exc}", "offers": []}
        report["sources"][label] = {"domain": domain, "queries": queries, "admitted_urls": admitted, "oracle_url": oracle_url, "oracle_in_admitted_urls": oracle_url in admitted, "direct_pdp": direct}
        print("P7_PHASE3=", json.dumps({label: report["sources"][label]}, ensure_ascii=False, sort_keys=True))
    Path("p7_phase3_forensics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
