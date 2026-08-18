from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk


class ExcelLiveUiMixin:
    """Truthful Excel-run counters/stages layered over the validated PDF desktop progress UI."""

    def _reset_excel_live_state(self) -> None:
        self._excel_live_counts = {
            "sources": 0,
            "validated": 0,
            "fields_resolved": 0,
            "fields_pending": 0,
            "fields_conflicted": 0,
            "queries": 0,
            "query_limit": 8,
            "pdf_found": 0,
            "pdf_used": 0,
        }
        self._excel_live_sources: set[str] = set()

    def _install_excel_progress(self):
        super()._install_excel_progress()
        tab = self._run_tab()
        if tab is None:
            return
        self.excel_live_counters = tk.StringVar(
            value="Fuentes: 0 · Validadas: 0 · Campos: 0 resueltos / 0 pendientes · Conflictos: 0 · Consultas: 0/8 · PDF: 0 encontrados / 0 usados"
        )
        ttk.Label(
            tab,
            textvariable=self.excel_live_counters,
            font=("Segoe UI", 9, "bold"),
            wraplength=1000,
            justify="left",
        ).pack(fill="x", pady=(3, 0))

    def _update_excel_live_counter_text(self) -> None:
        var = self.__dict__.get("excel_live_counters")
        if var is None:
            return
        counts = self._excel_live_counts
        var.set(
            f"Fuentes: {counts.get('sources', 0)} · Validadas: {counts.get('validated', 0)} · "
            f"Campos: {counts.get('fields_resolved', 0)} resueltos / {counts.get('fields_pending', 0)} pendientes · "
            f"Conflictos: {counts.get('fields_conflicted', 0)} · "
            f"Consultas: {counts.get('queries', 0)}/{counts.get('query_limit', 8)} · "
            f"PDF: {counts.get('pdf_found', 0)} encontrados / {counts.get('pdf_used', 0)} usados"
        )

    @staticmethod
    def _excel_stage_from_log(message: str) -> str | None:
        text = str(message or "")
        low = text.lower()
        if "smart identity:" in low:
            return "IDENTITY"
        if "smart plan:" in low:
            return "PLAN"
        if "smart source:" in low:
            return "SOURCE"
        if "smart query:" in low:
            return "QUERY"
        if "smart next_source:" in low:
            return "NEXT SOURCE"
        if "smart final:" in low:
            return "FINAL"
        if "smart fields:" in low:
            return "SEMANTIC RESOLUTION"
        if re.match(r"^\[\d+/\d+\]\s+", text):
            return "IDENTITY"
        if "probando:" in low or "buscando específicamente" in low or "búsqueda fabricante reforzada" in low:
            return "SEARCH"
        if "page_type=" in low or "evidence_allowed=" in low or "source_rejected=" in low:
            return "VALIDATE"
        if "fuente validada" in low or "gap fuente validada" in low:
            return "EXTRACT"
        if "pdf candidatos:" in low or "pdf validado:" in low or "pdf_download" in low:
            return "PDF"
        if "cobertura actual" in low or "cobertura tras documentos" in low or "segunda pasada" in low:
            return "SEMANTIC RESOLUTION"
        if "write_excel" in low or "escribiendo excel" in low:
            return "WRITE EXCEL"
        return None

    def _observe_excel_log(self, message: str, update_widget: bool = True) -> None:
        text = str(message or "")
        low = text.lower()

        source_match = re.search(r"\bprobando:\s*(https?://\S+)", text, flags=re.IGNORECASE)
        if source_match:
            url = source_match.group(1).rstrip(".,;)")
            if url not in self._excel_live_sources:
                self._excel_live_sources.add(url)
                self._excel_live_counts["sources"] += 1

        if "fuente validada:" in low or "gap fuente validada:" in low:
            self._excel_live_counts["validated"] += 1

        smart_query = re.search(r"SMART QUERY:\s*used=(\d+)\s+limit=(\d+)", text, flags=re.IGNORECASE)
        if smart_query:
            self._excel_live_counts["queries"] = int(smart_query.group(1))
            self._excel_live_counts["query_limit"] = int(smart_query.group(2))

        smart_fields = re.search(
            r"SMART FIELDS:\s*verificados=(\d+)\s+faltantes=(\d+)\s+conflictos=(\d+)",
            text,
            flags=re.IGNORECASE,
        )
        if smart_fields:
            self._excel_live_counts["fields_resolved"] = int(smart_fields.group(1))
            self._excel_live_counts["fields_pending"] = int(smart_fields.group(2))
            self._excel_live_counts["fields_conflicted"] = int(smart_fields.group(3))

        smart_final = re.search(
            r"SMART FINAL:\s*verified=(\d+)/(\d+)\s+missing=(\d+)\s+conflicts=(\d+)",
            text,
            flags=re.IGNORECASE,
        )
        if smart_final:
            self._excel_live_counts["fields_resolved"] = int(smart_final.group(1))
            self._excel_live_counts["fields_pending"] = int(smart_final.group(3))
            self._excel_live_counts["fields_conflicted"] = int(smart_final.group(4))

        coverage = re.search(
            r"cobertura actual:\s*(\d+)\s*/\s*(\d+).*?pendientes\s*=\s*(\d+)",
            text,
            flags=re.IGNORECASE,
        )
        if coverage and not smart_fields:
            self._excel_live_counts["fields_resolved"] = int(coverage.group(1))
            self._excel_live_counts["fields_pending"] = int(coverage.group(3))
        else:
            pending = re.search(r"cobertura tras documentos:\s*pendientes\s*=\s*(\d+)", text, flags=re.IGNORECASE)
            if pending:
                self._excel_live_counts["fields_pending"] = int(pending.group(1))

        pdf_candidates = re.search(r"PDF CANDIDATOS:\s*(\d+)", text, flags=re.IGNORECASE)
        if pdf_candidates:
            self._excel_live_counts["pdf_found"] += int(pdf_candidates.group(1))
        if "pdf validado:" in low:
            self._excel_live_counts["pdf_used"] += 1

        if update_widget:
            self._update_excel_live_counter_text()

    def _excel_progress_start(self, total: int):
        self._reset_excel_live_state()
        result = super()._excel_progress_start(total)
        try:
            self.after(0, self._update_excel_live_counter_text)
        except Exception:
            pass
        return result

    def _excel_progress_log(self, message):
        text = str(message)
        self._observe_excel_log(text, update_widget=False)
        try:
            self.after(0, self._update_excel_live_counter_text)
        except Exception:
            pass
        result = super()._excel_progress_log(message)
        stage = self._excel_stage_from_log(text)
        if stage == "IDENTITY":
            self._excel_progress_stage("Resolviendo identidad…")
        elif stage == "PLAN":
            self._excel_progress_stage("Planificando evidencia…")
        elif stage == "SOURCE":
            self._excel_progress_stage("Consultando mejor fuente…")
        elif stage == "QUERY":
            self._excel_progress_stage("Buscando evidencia…")
        elif stage == "NEXT SOURCE":
            self._excel_progress_stage("Probando siguiente fuente…")
        elif stage == "FINAL":
            self._excel_progress_stage("Consolidando evidencia final…")
        elif stage == "PDF":
            self._excel_progress_stage("Procesando PDF…")
        elif stage == "SEMANTIC RESOLUTION":
            self._excel_progress_stage("Resolución semántica…")
        elif stage == "VALIDATE":
            self._excel_progress_stage("Validando fuente…")
        return result
