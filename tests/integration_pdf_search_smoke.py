from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from product_intelligence.document_discovery import discover_product_documents
from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_download import download_pdf
from product_intelligence.pdf_search_trace import PdfSearchTrace

PART_NUMBERS = [
    "JBLQ350WLBLKAM",
    "JBLENDURRUN3BTBAM",
    "JBLT530CBLKAM",
]


def main() -> int:
    rows = []
    architecture_failures = 0
    for part_number in PART_NUMBERS:
        trace = PdfSearchTrace(part_number)
        try:
            docs = discover_product_documents(
                ProductIdentity(mpn=part_number, model=part_number),
                limit=6,
                timeout=12,
                trace=trace,
            )
            downloads = []
            with TemporaryDirectory(prefix=f"pdf-smoke-{part_number}-") as tmp:
                for doc in docs[:2]:
                    try:
                        downloaded = download_pdf(doc.url, Path(tmp), timeout=20, trace=trace)
                        downloads.append({
                            "url": doc.url,
                            "ok": True,
                            "final_url": downloaded.final_url,
                            "content_type": downloaded.content_type,
                            "bytes": downloaded.size_bytes,
                            "sha256": downloaded.sha256,
                        })
                    except Exception as exc:
                        downloads.append({
                            "url": doc.url,
                            "ok": False,
                            "error": f"{type(exc).__name__}: {exc}",
                        })

            summary = trace.summary()
            row = {
                "part_number": part_number,
                **summary,
                "pdf_candidates": len(docs),
                "candidate_urls": [doc.url for doc in docs],
                "downloads": downloads,
                "browser_fallback_executed": any(
                    event.get("event") == "PDF_SEARCH_BROWSER_FALLBACK" for event in trace.events
                ),
                "queries_attempted": [
                    event.get("query") for event in trace.events if event.get("event") == "PDF_SEARCH_QUERY"
                ],
                "error": None,
            }
            if summary["queries"] <= 0:
                architecture_failures += 1
        except Exception as exc:
            architecture_failures += 1
            row = {
                "part_number": part_number,
                "queries": trace.summary()["queries"],
                "pdf_candidates": 0,
                "candidate_urls": [],
                "downloads": [],
                "browser_fallback_executed": any(
                    event.get("event") == "PDF_SEARCH_BROWSER_FALLBACK" for event in trace.events
                ),
                "queries_attempted": [
                    event.get("query") for event in trace.events if event.get("event") == "PDF_SEARCH_QUERY"
                ],
                "error": f"{type(exc).__name__}: {exc}",
            }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    Path("pdf-search-smoke.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 1 if architecture_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
