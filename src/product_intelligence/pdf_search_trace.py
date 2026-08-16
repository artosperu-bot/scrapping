from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PdfSearchTrace:
    product_key: str
    events: list[dict] = field(default_factory=list)

    def emit(self, event: str, **data) -> None:
        self.events.append({"event": event, **data})

    def summary(self) -> dict[str, int]:
        def total(name: str, key: str = "result_count") -> int:
            return sum(int(row.get(key, 0) or 0) for row in self.events if row.get("event") == name)

        return {
            "queries": sum(1 for row in self.events if row.get("event") == "PDF_SEARCH_QUERY"),
            "http_results": total("PDF_SEARCH_HTTP_RESULT"),
            "browser_results": total("PDF_SEARCH_BROWSER_RESULT"),
            "landing_pages": sum(1 for row in self.events if row.get("event") == "PDF_LANDING_INSPECTED"),
            "pdf_links": sum(1 for row in self.events if row.get("event") == "PDF_LINK_DISCOVERED"),
            "downloads_ok": sum(1 for row in self.events if row.get("event") == "PDF_DOWNLOAD_OK"),
            "downloads_rejected": sum(1 for row in self.events if row.get("event") == "PDF_DOWNLOAD_REJECTED"),
            "prefetch_rejected": sum(1 for row in self.events if row.get("event") == "PDF_CANDIDATE_REJECTED_PRE_FETCH"),
            "duplicates": sum(1 for row in self.events if row.get("event") == "PDF_CANDIDATE_DUPLICATE"),
            "exact_pdps": sum(1 for row in self.events if row.get("event") == "PDF_EXACT_PDP_FOUND"),
            "pdp_pivots": sum(1 for row in self.events if row.get("event") == "PDF_PDP_PIVOT"),
            "provenance_bound": sum(1 for row in self.events if row.get("event") == "PDF_PROVENANCE_BOUND"),
        }


def format_trace_lines(trace: PdfSearchTrace) -> list[str]:
    lines: list[str] = []
    for row in trace.events:
        event = row.get("event")
        if event == "PDF_SEARCH_QUERY":
            lines.append(f"  PDF SEARCH query: {row.get('query', '')}")
        elif event == "PDF_SEARCH_HTTP_RESULT":
            lines.append(f"  HTTP SEARCH: {int(row.get('result_count', 0) or 0)} resultados")
        elif event == "PDF_SEARCH_BROWSER_FALLBACK":
            lines.append("  BROWSER FALLBACK: activado")
        elif event == "PDF_SEARCH_BROWSER_RESULT":
            lines.append(f"  BROWSER SEARCH: {int(row.get('result_count', 0) or 0)} resultados")
        elif event == "PDF_CANDIDATE_REJECTED_PRE_FETCH":
            lines.append(f"  PDF CANDIDATO DESCARTADO PRE-FETCH: {row.get('reason', '')} · {row.get('url', '')}")
        elif event == "PDF_CANDIDATE_DUPLICATE":
            lines.append(f"  PDF CANDIDATO DUPLICADO: {row.get('url', '')}")
        elif event == "PDF_EXACT_PDP_FOUND":
            lines.append(f"  PDP EXACTA: {row.get('url', '')}")
        elif event == "PDF_PDP_PIVOT":
            lines.append(f"  PDP PIVOT: {int(row.get('count', 0) or 0)} candidato(s) exactos")
        elif event == "PDF_LANDING_INSPECTED":
            lines.append(f"  LANDING INSPECCIONADA: {row.get('url', '')}")
        elif event == "PDF_LINK_DISCOVERED":
            lines.append(f"  PDF LINK: {row.get('url', '')}")
        elif event == "PDF_PROVENANCE_BOUND":
            lines.append(f"  PDF PROVENANCE BOUND: {row.get('parent_url', '')} -> {row.get('url', '')}")
        elif event == "PDF_DOWNLOAD_OK":
            lines.append(f"  PDF DOWNLOAD OK: {row.get('url', '')} ({int(row.get('bytes', 0) or 0)} bytes)")
        elif event == "PDF_DOWNLOAD_REJECTED":
            lines.append(f"  PDF DOWNLOAD RECHAZADO: {row.get('url', '')} · {row.get('reason', '')}")

    summary = trace.summary()
    lines.append(
        "  PDF RESUMEN: "
        f"queries={summary['queries']} http_results={summary['http_results']} "
        f"browser_results={summary['browser_results']} landing_pages={summary['landing_pages']} "
        f"pdf_links={summary['pdf_links']} downloads_ok={summary['downloads_ok']} "
        f"downloads_rejected={summary['downloads_rejected']} "
        f"prefetch_rejected={summary['prefetch_rejected']} duplicates={summary['duplicates']} "
        f"exact_pdps={summary['exact_pdps']} pdp_pivots={summary['pdp_pivots']} "
        f"provenance_bound={summary['provenance_bound']}"
    )
    if not summary["pdf_links"] and not summary["downloads_ok"]:
        lines.append(
            "  SIN PDF VALIDADO: "
            f"queries={summary['queries']} http_results={summary['http_results']} "
            f"browser_results={summary['browser_results']} landing_pages={summary['landing_pages']} "
            f"pdf_links={summary['pdf_links']}"
        )
    return lines