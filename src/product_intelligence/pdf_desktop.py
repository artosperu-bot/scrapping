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
    discover_pdf_candidates,
    download_pdf,
    emit_pdf_event,
    pdf_evidence_enabled,
    pdf_evidence_scope,
    pdf_output_root,
)
from .provider_runtime import provider_run_scope
from .provider_settings import ProviderSettings

_BASE_EXTRACT_PAGE = pipeline_module.extract_page
_BASE_EXTRACT_PDF = pipeline_module.extract_pdf
_PROVIDER_OPTION_KEYS = (
    "ocr_space_enabled",
    "mistral_enabled",
    "mistral_model",
    "request_timeout",
)


def _pdf_aware_extract_page(html, base_url, identity_terms=None):
    page = _BASE_EXTRACT_PAGE(html, base_url, identity_terms)
    pdfs = list(page.get("pdfs") or [])
    for candidate in discover_pdf_candidates(html, base_url):
        if candidate.url not in pdfs:
            pdfs.append(candidate.url)
    page["pdfs"] = pdfs
    return page


def _safe_pdf_name(url: str) -> str:
    raw = Path(urlparse(url).path).name
    if not raw.lower().endswith(".pdf"):
        raw = f"document_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]}.pdf"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw) or "document.pdf"


def _scoped_extract_pdf(url: str, match_level: str = "HIGH", confidence: float = .90):
    if not pdf_evidence_enabled():
        emit_pdf_event("PDF_SKIPPED", url=url, detail="Evidencia PDF desactivada")
        return "", []
    emit_pdf_event("PDF_FOUND", url=url, detail="PDF candidato")
    text, evidence = _BASE_EXTRACT_PDF(url, match_level, confidence)
    local_path = None
    root = pdf_output_root()
    if root:
        try:
            local_path = download_pdf(url, Path(root) / "pdf_evidence" / _safe_pdf_name(url))
            emit_pdf_event("PDF_DOWNLOADED", url=url, local_path=str(local_path), detail="PDF guardado")
        except Exception as exc:
            emit_pdf_event("PDF_ERROR", url=url, detail=f"No se pudo guardar PDF: {type(exc).__name__}")
    methods = set()
    for row in evidence:
        selector = str(row.selector or "")
        if local_path:
            row.selector = f"{selector};pdf_path={local_path}" if selector else f"pdf_path={local_path}"
        if "method=OCR" in selector:
            methods.add("OCR")
        elif "method=TEXT" in selector:
            methods.add("TEXT")
    if "TEXT" in methods or (text and not methods):
        emit_pdf_event("PDF_TEXT", url=url, detail="Texto PDF extraído")
    if "OCR" in methods:
        emit_pdf_event("PDF_OCR", url=url, detail="OCR aplicado como fallback")
    return text, evidence


def _install_hooks():
    if getattr(pipeline_module, "_stech_pdf_hooks", False):
        return
    pipeline_module.extract_page = _pdf_aware_extract_page
    pipeline_module.extract_pdf = _scoped_extract_pdf
    pipeline_module._stech_pdf_hooks = True


_install_hooks()


class App(IsolatedApp):
    def __init__(self):
        super().__init__()
        self.use_pdf_evidence = tk.BooleanVar(value=True)
        self._install_pdf_option()

    def _install_pdf_option(self):
        tab_ref = self._workspace_tabs.get("run")
        if tab_ref is None:
            return
        tab = self.nametowidget(str(tab_ref)) if isinstance(tab_ref, str) else tab_ref
        box = ttk.LabelFrame(tab, text="Evidencia documental", padding=8)
        box.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(box, text="Usar PDFs como evidencia", variable=self.use_pdf_evidence).pack(anchor="w")
        ttk.Label(box, text="Detecta fichas/manuales, valida el producto, descarga el PDF y usa OCR solo si falta texto.").pack(anchor="w", pady=(2, 0))

    def run(self):
        if not self.excel.get() or self.preflight is None:
            return super().run()
        selected = self._selected_source_index()
        if selected is not None:
            self.save_urls_for_selected()
        products = []
        for index in range(len(self.product_rows)):
            snap = self._product_snapshot(index, self.manual_urls.get(index, []))
            if snap is None:
                messagebox.showerror("Identidad", "Hay productos sin identidad válida. Corrígelos antes de ejecutar.")
                return
            products.append(snap)

        persisted = ProviderSettings().as_dict()
        options = {"use_pdf_evidence": bool(self.use_pdf_evidence.get())}
        for key in _PROVIDER_OPTION_KEYS:
            options[key] = persisted.get(key)

        snapshot = ExecutionSnapshot.create(
            "EXCEL", self.out.get(), products, workbook=self.excel.get(), overwrite=self.overwrite.get(),
            options=options,
        )
        self._active_snapshots[snapshot.run_id] = snapshot
        self.runbtn.configure(state="disabled")
        self._show_workspace("audit")
        enabled = bool(snapshot.option("use_pdf_evidence", True))
        self._audit(snapshot, status="STARTED", stage="inicio", detail=f"Scraping Excel iniciado. PDF={'ON' if enabled else 'OFF'}")

        def work(job=snapshot):
            def on_pdf(event):
                stage = str(event.get("stage") or "PDF")
                status = "ERROR" if stage == "PDF_ERROR" else "REJECTED" if stage == "PDF_REJECTED" else "FOUND" if stage in {"PDF_FOUND", "PDF_DOWNLOADED", "PDF_TEXT", "PDF_OCR"} else "PROGRESS"
                self._audit(job, status=status, stage=stage, source="PDF", url=str(event.get("url") or ""), detail=str(event.get("detail") or ""), result=str(event.get("local_path") or ""))

            def on_provider(event, data):
                detail = ", ".join(f"{key}={value}" for key, value in sorted((data or {}).items()))
                status = "REJECTED" if event == "MISTRAL_DESCRIPTION_REJECTED" else "PROGRESS"
                self._audit(
                    job,
                    status=status,
                    stage=event,
                    source=str((data or {}).get("provider") or "PROVIDER"),
                    detail=detail,
                )

            provider_settings = {key: job.option(key) for key in _PROVIDER_OPTION_KEYS}
            try:
                identities = [p.identity for p in job.products]
                urls = [list(p.manual_urls) for p in job.products]
                self.emit(f"=== {job.run_id} INICIO SCRAPING ===")
                with provider_run_scope(provider_settings, on_provider):
                    with pdf_evidence_scope(bool(job.option("use_pdf_evidence", True)), job.output_root, on_pdf):
                        result = run_batch(job.workbook, job.output_root, overwrite=job.overwrite, log=self.emit, manual_identities=identities, manual_source_urls=urls)
                self.emit(json.dumps(result, ensure_ascii=False, indent=2))
                self._audit(job, status="DONE", stage="final", detail="Scraping Excel completado.", result=str(result.get("output_excel") or ""))
                self.after(0, lambda: messagebox.showinfo("Terminado", f"Excel: {result['output_excel']}"))
            except Exception as exc:
                self.emit(traceback.format_exc())
                self._audit(job, status="ERROR", stage="fatal", detail=str(exc))
                self.after(0, lambda e=str(exc): messagebox.showerror("Error", e))
            finally:
                self._active_snapshots.pop(job.run_id, None)
                self.after(0, lambda: self.runbtn.configure(state="normal"))
        threading.Thread(target=work, daemon=True).start()


def main():
    App().mainloop()
