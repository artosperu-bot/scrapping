from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from product_intelligence.part_number_pdf_search import search_product_pdfs_by_part_number

PART_NUMBERS = ["JBLQ350WLBLKAM", "JBLENDURRUN3BTBAM", "JBLT530CBLKAM"]


def _queries(lines):
    marker = "PDF SEARCH query:"
    return [str(x).split(marker, 1)[1].strip() for x in lines if marker in str(x)]


def main() -> int:
    rows, failures = [], 0
    with TemporaryDirectory(prefix="pdf-smoke-") as tmp:
        for part in PART_NUMBERS:
            logs, events = [], []
            try:
                result = search_product_pdfs_by_part_number(part, Path(tmp) / part, limit=8, timeout=10, log=logs.append, on_event=events.append)
                ident = result.resolved.identity
                model = str(ident.model or ident.product_name or "").strip()
                queries = _queries(logs)
                urls = [str(e.get("url") or "") for e in events if e.get("type") == "candidate"]
                canonical_used = bool(model) and any(model.lower() in q.lower() for q in queries)
                gates = []
                if result.validated_count < 1: gates.append("ZERO_VALIDATED_PDF")
                if any("connect.facebook.net" in u.lower() for u in urls): gates.append("FALSE_FACEBOOK_PDF_CANDIDATE")
                if part == "JBLENDURRUN3BTBAM" and (model.lower() == part.lower() or not canonical_used): gates.append("CANONICAL_MODEL_NOT_USED_IN_QUERY")
                row = {"part_number": part, "identity_resolved": bool(ident.brand and model and model.lower() != part.lower()), "brand": ident.brand, "canonical_model": model or None, "identity_confidence": result.resolved.confidence, "official_domain": result.resolved.official_domain, "queries": len(queries), "queries_attempted": queries, "candidate_urls": urls, "validated_pdfs": result.validated_count, "official_pdfs": sum(bool(x.candidate.likely_official) for x in result.candidates), "provenance_bound": sum(bool(x.inspection.identity_provenance_bound) for x in result.candidates), "downloads_ok": result.downloaded_count, "downloads_rejected": result.rejected_count, "stop_reason": "SUFFICIENT_VALIDATED_PDFS" if result.validated_count else "SEARCH_BUDGET_EXHAUSTED", "gate_failures": gates, "error": None}
                failures += bool(gates)
            except Exception as exc:
                failures += 1
                row = {"part_number": part, "validated_pdfs": 0, "gate_failures": ["RUNTIME_ERROR"], "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row); print(json.dumps(row, ensure_ascii=False))
    Path("pdf-search-smoke.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__": raise SystemExit(main())
