from __future__ import annotations

import hashlib
import json
import re
import threading
import traceback
from pathlib import Path
from urllib.parse import urlparse
import tkinter as tk
from tkinter import messagebox, ttk

from . import pipeline as pipeline_module
from .batch import run_batch
from .execution_context import ExecutionSnapshot
from .isolated_desktop import App as IsolatedApp
from .pdf_evidence import (
    discover_pdf_candidates, download_pdf, emit_pdf_event, pdf_evidence_enabled,
    pdf_evidence_scope, pdf_output_root,
)
from .progress_animation import ProgressAnimation
from .provider_runtime import provider_run_scope
from .provider_settings import ProviderSettings

_BASE_EXTRACT_PAGE = pipeline_module.extract_page
_BASE_EXTRACT_PDF = pipeline_module.extract_pdf
_PROVIDER_OPTION_KEYS = ("ocr_space_enabled", "mistral_enabled", "mistral_model", "request_timeout")


def _pdf_aware_extract_page(html, base_url, identity_terms=None):
    page = _BASE_EXTRACT_PAGE(html, base_url, identity_terms)
    pdfs = list(page.get("pdfs") or [])
    for candidate in discover_pdf_candidates(html, base_url):
        if candidate.url not in pdfs: pdfs.append(candidate.url)
    page["pdfs"] = pdfs
    return page


def _safe_pdf_name(url: str) -> str:
    raw = Path(urlparse(url).path).name
    if not raw.lower().endswith(".pdf"): raw = f"document_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]}.pdf"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw) or "document.pdf"


def _scoped_extract_pdf(url: str, match_level: str = "HIGH", confidence: float = .90):
    if not pdf_evidence_enabled():
        emit_pdf_event("PDF_SKIPPED", url=url, detail="Evidencia PDF desactivada"); return "", []
    emit_pdf_event("PDF_FOUND", url=url, detail="PDF candidato")
    text, evidence = _BASE_EXTRACT_PDF(url, match_level, confidence)
    local_path = None; root = pdf_output_root()
    if root:
        try:
            local_path = download_pdf(url, Path(root) / "pdf_evidence" / _safe_pdf_name(url))
            emit_pdf_event("PDF_DOWNLOADED", url=url, local_path=str(local_path), detail="PDF guardado")
        except Exception as exc:
            emit_pdf_event("PDF_ERROR", url=url, detail=f"No se pudo guardar PDF: {type(exc).__name__}")
    methods = set()
    for row in evidence:
        selector = str(row.selector or "")
        if local_path: row.selector = f"{selector};pdf_path={local_path}" if selector else f"pdf_path={local_path}"
        if "method=OCR" in selector: methods.add("OCR")
        elif "method=TEXT" in selector: methods.add("TEXT")
    if "TEXT" in methods or (text and not methods): emit_pdf_event("PDF_TEXT", url=url, detail="Texto PDF extraído")
    if "OCR" in methods: emit_pdf_event("PDF_OCR", url=url, detail="OCR aplicado como fallback")
    return text, evidence


def _install_hooks():
    if getattr(pipeline_module, "_stech_pdf_hooks", False): return
    pipeline_module.extract_page = _pdf_aware_extract_page; pipeline_module.extract_pdf = _scoped_extract_pdf; pipeline_module._stech_pdf_hooks = True


_install_hooks()


class App(IsolatedApp):
    def __init__(self):
        super().__init__()
        self.use_pdf_evidence = tk.BooleanVar(value=True)
        self._excel_progress_total = 0
        self._excel_progress_completed = 0
        self._install_pdf_option()
        self._install_excel_progress()

    def _run_tab(self):
        tab_ref = self._workspace_tabs.get("run")
        return self.nametowidget(str(tab_ref)) if isinstance(tab_ref, str) else tab_ref

    def _install_pdf_option(self):
        tab = self._run_tab()
        if tab is None: return
        box = ttk.LabelFrame(tab, text="Evidencia documental", padding=8); box.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(box, text="Usar PDFs como evidencia", variable=self.use_pdf_evidence).pack(anchor="w")
        ttk.Label(box, text="Detecta fichas/manuales, valida el producto, descarga el PDF y usa OCR solo si falta texto.").pack(anchor="w", pady=(2, 0))

    def _install_excel_progress(self):
        tab = self._run_tab()
        if tab is None: return
        box = ttk.LabelFrame(tab, text="Progreso del proceso", style="Card.TLabelframe", padding=8); box.pack(fill="x", pady=(8, 0))
        self.excel_progress_animation = ProgressAnimation(box, width=180, height=105); self.excel_progress_animation.pack(anchor="center")
        self.excel_progress_status = tk.StringVar(value="Listo para procesar")
        ttk.Label(box, textvariable=self.excel_progress_status, font=("Segoe UI", 9, "bold")).pack(anchor="center", pady=(2, 5))
        row = ttk.Frame(box); row.pack(fill="x")
        self.excel_progress_bar = ttk.Progressbar(row, maximum=100, mode="determinate"); self.excel_progress_bar.pack(side="left", fill="x", expand=True)
        self.excel_progress_value = tk.StringVar(value="0%")
        ttk.Label(row, textvariable=self.excel_progress_value, width=8).pack(side="left", padx=(8, 0))

    def _excel_progress_start(self, total: int):
        def apply():
            self._excel_progress_total = max(0, int(total)); self._excel_progress_completed = 0
            self.excel_progress_bar["value"] = 0; self.excel_progress_value.set("0%")
            self.excel_progress_status.set("Procesando…"); self.excel_progress_animation.set_running("Procesando…")
        self.after(0, apply)

    def _excel_progress_stage(self, text: str):
        self.after(0, lambda t=str(text): (self.excel_progress_status.set(t), self.excel_progress_animation.set_running(t)))

    def _excel_progress_log(self, message):
        text = str(message); self.emit(text)
        match = re.match(r"^\[(\d+)/(\d+)\]\s+(.+)$", text)
        if match:
            position, total, label = int(match.group(1)), int(match.group(2)), match.group(3)
            def apply():
                self._excel_progress_total = total; self._excel_progress_completed = max(0, position - 1)
                pct = int((self._excel_progress_completed / max(1, total)) * 100)
                self.excel_progress_bar["value"] = pct; self.excel_progress_value.set(f"{pct}%")
                status = f"Procesando producto {position} de {total} · {label}"; self.excel_progress_status.set(status); self.excel_progress_animation.set_running(status)
            self.after(0, apply); return
        low = text.lower()
        if "probando:" in low or "buscando específicamente" in low: self._excel_progress_stage("Buscando fuentes…")
        elif "fuente validada" in low: self._excel_progress_stage("Extrayendo datos…")
        elif "cobertura actual" in low or "segunda pasada" in low: self._excel_progress_stage("Analizando evidencia…")

    def _excel_progress_done(self):
        def apply():
            self._excel_progress_completed = self._excel_progress_total; self.excel_progress_bar["value"] = 100; self.excel_progress_value.set("100%")
            self.excel_progress_status.set("Proceso completado"); self.excel_progress_animation.set_completed("Proceso completado")
        self.after(0, apply)

    def _excel_progress_error(self, error: str):
        self.after(0, lambda e=str(error): (self.excel_progress_status.set(e), self.excel_progress_animation.set_error(e)))

    def run(self):
        if not self.excel.get() or self.preflight is None: return super().run()
        selected = self._selected_source_index()
        if selected is not None: self.save_urls_for_selected()
        products = []
        for index in range(len(self.product_rows)):
            snap = self._product_snapshot(index, self.manual_urls.get(index, []))
            if snap is None: messagebox.showerror("Identidad", "Hay productos sin identidad válida. Corrígelos antes de ejecutar."); return
            products.append(snap)
        persisted = ProviderSettings().as_dict(); options = {"use_pdf_evidence": bool(self.use_pdf_evidence.get())}
        for key in _PROVIDER_OPTION_KEYS: options[key] = persisted.get(key)
        snapshot = ExecutionSnapshot.create("EXCEL", self.out.get(), products, workbook=self.excel.get(), overwrite=self.overwrite.get(), options=options)
        self._active_snapshots[snapshot.run_id] = snapshot; self.runbtn.configure(state="disabled"); self._show_workspace("audit")
        enabled = bool(snapshot.option("use_pdf_evidence", True)); self._audit(snapshot, status="STARTED", stage="inicio", detail=f"Scraping Excel iniciado. PDF={'ON' if enabled else 'OFF'}")
        self._excel_progress_start(len(products))

        def work(job=snapshot):
            def on_pdf(event):
                stage = str(event.get("stage") or "PDF")
                status = "ERROR" if stage == "PDF_ERROR" else "REJECTED" if stage == "PDF_REJECTED" else "FOUND" if stage in {"PDF_FOUND", "PDF_DOWNLOADED", "PDF_TEXT", "PDF_OCR"} else "PROGRESS"
                self._audit(job, status=status, stage=stage, source="PDF", url=str(event.get("url") or ""), detail=str(event.get("detail") or ""), result=str(event.get("local_path") or ""))
                if stage == "PDF_OCR": self._excel_progress_stage("Procesando PDF con OCR…")
                elif stage in {"PDF_FOUND", "PDF_DOWNLOADED", "PDF_TEXT"}: self._excel_progress_stage("Procesando PDF…")
            def on_provider(event, data):
                detail = ", ".join(f"{key}={value}" for key, value in sorted((data or {}).items())); status = "REJECTED" if event == "MISTRAL_DESCRIPTION_REJECTED" else "PROGRESS"
                self._audit(job, status=status, stage=event, source=str((data or {}).get("provider") or "PROVIDER"), detail=detail)
                if "MISTRAL" in event: self._excel_progress_stage("Generando descripción…")
                elif "OCR" in event: self._excel_progress_stage("Procesando OCR…")
            provider_settings = {key: job.option(key) for key in _PROVIDER_OPTION_KEYS}
            try:
                identities = [p.identity for p in job.products]; urls = [list(p.manual_urls) for p in job.products]
                self.emit(f"=== {job.run_id} INICIO SCRAPING ===")
                with provider_run_scope(provider_settings, on_provider):
                    with pdf_evidence_scope(bool(job.option("use_pdf_evidence", True)), job.output_root, on_pdf):
                        result = run_batch(job.workbook, job.output_root, overwrite=job.overwrite, log=self._excel_progress_log, manual_identities=identities, manual_source_urls=urls)
                self.emit(json.dumps(result, ensure_ascii=False, indent=2)); self._audit(job, status="DONE", stage="final", detail="Scraping Excel completado.", result=str(result.get("output_excel") or "")); self._excel_progress_done()
                self.after(0, lambda: messagebox.showinfo("Terminado", f"Excel: {result['output_excel']}"))
            except Exception as exc:
                self.emit(traceback.format_exc()); self._audit(job, status="ERROR", stage="fatal", detail=str(exc)); self._excel_progress_error(str(exc)); self.after(0, lambda e=str(exc): messagebox.showerror("Error", e))
            finally:
                self._active_snapshots.pop(job.run_id, None); self.after(0, lambda: self.runbtn.configure(state="normal"))
        threading.Thread(target=work, daemon=True).start()


def main(): App().mainloop()
