from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from .real_pdf_review_shell import review_gate_missing_indices


@dataclass
class PdfExecuteRuntimeState:
    """Presentation-only state for the PDF activity shown in Ejecutar."""

    query_position: int = 0
    query_limit: int = 8
    found: int = 0
    downloaded: int = 0
    validated: int = 0
    rejected: int = 0
    progress: int = 0
    status: str = "Listo"
    _found_keys: set[str] = field(default_factory=set, repr=False)
    _downloaded_keys: set[str] = field(default_factory=set, repr=False)
    _validated_keys: set[str] = field(default_factory=set, repr=False)
    _rejected_keys: set[str] = field(default_factory=set, repr=False)

    def _advance(self, value: int) -> None:
        self.progress = max(self.progress, min(100, max(0, int(value))))

    def apply(self, event: dict) -> None:
        kind = str(event.get("type") or "")
        if kind == "stage" and str(event.get("stage") or "") == "IDENTITY":
            self.status = "Resolviendo identidad"
            self._advance(4)
        elif kind == "query":
            self.query_position = max(self.query_position, int(event.get("position") or 0))
            self.query_limit = max(1, int(event.get("limit") or self.query_limit or 8))
            self.status = f"Búsqueda {self.query_position}/{self.query_limit}"
            self._advance(8 + int(42 * (self.query_position / self.query_limit)))
        elif kind == "identity":
            brand = str(event.get("brand") or "").strip()
            model = str(event.get("model") or "").strip()
            self.status = f"Identidad: {' '.join(x for x in (brand, model) if x) or 'resuelta'}"
            self._advance(10)
        elif kind == "candidate":
            key = str(event.get("url") or event.get("title") or event.get("position") or "").strip().lower()
            if key:
                self._found_keys.add(key)
            self.found = max(self.found, len(self._found_keys), int(event.get("position") or 0))
            self.status = "PDF encontrado"
            self._advance(55)
        elif kind == "download":
            status = str(event.get("status") or "").upper()
            key = str(event.get("local_path") or event.get("url") or "").strip().lower()
            if status == "FINISHED":
                if key:
                    self._downloaded_keys.add(key)
                self.downloaded = max(self.downloaded, len(self._downloaded_keys))
                self.status = "PDF descargado"
                self._advance(70)
            else:
                self.status = "Descargando PDF"
                self._advance(62)
        elif kind == "validated":
            row = event.get("row")
            inspection = getattr(row, "inspection", None)
            key = str(
                getattr(inspection, "local_path", "")
                or event.get("url")
                or len(self._validated_keys) + 1
            ).strip().lower()
            if key:
                self._validated_keys.add(key)
            self.validated = max(self.validated, len(self._validated_keys))
            self.status = "PDF aceptado"
            self._advance(84)
        elif kind == "rejected":
            key = str(event.get("url") or event.get("reason") or len(self._rejected_keys) + 1).strip().lower()
            if key:
                self._rejected_keys.add(key)
            self.rejected = max(self.rejected, len(self._rejected_keys))
            self.status = "PDF rechazado"
            self._advance(84)
        elif kind == "duplicate":
            self.status = "PDF duplicado omitido"
            self._advance(84)
        elif kind == "final_result":
            payload = event.get("result")
            error = event.get("error")
            if error:
                self.status = f"Error PDF: {error}"
                return
            if payload is not None:
                self.found = int(getattr(payload, "discovered_count", self.found) or 0)
                self.downloaded = int(getattr(payload, "downloaded_count", self.downloaded) or 0)
                self.validated = int(getattr(payload, "validated_count", self.validated) or 0)
                self.rejected = int(getattr(payload, "rejected_count", self.rejected) or 0)
                self.progress = 100
                self.status = "Revisión PDF lista"


class PdfDesktopE2EMixin:
    """Make the certified PDF engine observable and tangible in the packaged desktop.

    Search/ranking/identity stays in the existing P60 engine. This mixin only bridges
    its main-thread review events into the global desktop log/progress and exposes the
    folders where validated documents are retained.
    """

    def _pdf_review_root(self) -> Path:
        out_var = self.__dict__.get("out") or self.__dict__.get("out_var")
        output = ""
        if out_var is not None:
            try:
                output = str(out_var.get() or "").strip()
            except Exception:
                output = ""
        return Path(output) if output else (Path.home() / "ProductIntelligence_Output")

    @staticmethod
    def _pdf_safe_identifier(value: object) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "producto"))

    def _pdf_identifier_for_index(self, index: int | None) -> str:
        identity = None
        if index is not None:
            try:
                identity = self._identity_for_index(index)
            except Exception:
                identity = None
        value = "producto"
        if identity is not None:
            value = str(
                identity.mpn
                or identity.ean
                or identity.upc
                or identity.gtin
                or identity.model
                or identity.product_name
                or "producto"
            )
        return self._pdf_safe_identifier(value)

    def _pdf_review_identifier(self) -> str:
        index = None
        try:
            index = self._pdf_review_product_index()
        except Exception:
            pass
        return self._pdf_identifier_for_index(index)

    def _pdf_folder_for_index(self, index: int | None) -> Path:
        root = self._pdf_review_root()
        label = self._pdf_identifier_for_index(index)
        review = root / "pdf_review" / label
        evidence = root / "pdf_evidence" / label
        if review.exists():
            return review
        if evidence.exists():
            return evidence
        review.mkdir(parents=True, exist_ok=True)
        return review

    def _pdf_review_current_folder(self) -> Path:
        index = None
        try:
            index = self._pdf_review_product_index()
        except Exception:
            pass
        return self._pdf_folder_for_index(index)

    @staticmethod
    def _open_pdf_folder_path(folder: Path) -> None:
        if hasattr(os, "startfile"):
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _pdf_review_open_folder(self):
        folder = self._pdf_review_current_folder()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            self._open_pdf_folder_path(folder)
        except Exception as exc:
            messagebox.showerror("Revisión PDF", f"No se pudo abrir la carpeta:\n{folder}\n\n{type(exc).__name__}: {exc}")
            return
        status = self.__dict__.get("pdf_review_status")
        if status is not None:
            status.set(f"Carpeta PDFs: {folder}")

    def _pdf_execute_open_folder(self):
        index = getattr(self, "_pdf_execute_active_index", None)
        folder = self._pdf_folder_for_index(index)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            self._open_pdf_folder_path(folder)
        except Exception as exc:
            messagebox.showerror("PDF · Ejecución", f"No se pudo abrir la carpeta:\n{folder}\n\n{type(exc).__name__}: {exc}")
            return
        folder_var = self.__dict__.get("pdf_execute_folder")
        if folder_var is not None:
            folder_var.set(f"Carpeta: {folder}")

    def _install_pdf_review_workspace(self):
        result = super()._install_pdf_review_workspace()
        button = ttk.Button(
            self.pdf_review_tab,
            text="Abrir carpeta PDFs",
            command=self._pdf_review_open_folder,
        )
        button.place(relx=1.0, y=8, anchor="ne")
        self.pdf_review_open_folder_button = button
        return result

    def _install_excel_progress(self):
        result = super()._install_excel_progress()
        tab = self._run_tab()
        if tab is None:
            return result

        self._pdf_execute_states: dict[int, PdfExecuteRuntimeState] = {}
        self._pdf_execute_results: dict[int, int] = {}
        self._pdf_execute_active_index: int | None = None

        box = ttk.LabelFrame(tab, text="PDF · seguimiento en esta ejecución", padding=8)
        box.pack(fill="x", pady=(8, 0))
        self.pdf_execute_panel = box

        top = ttk.Frame(box)
        top.pack(fill="x")
        self.pdf_execute_status = tk.StringVar(value="PDF · listo")
        ttk.Label(top, textvariable=self.pdf_execute_status, font=("Segoe UI", 9, "bold")).pack(side="left", fill="x", expand=True)
        self.pdf_execute_open_folder_button = ttk.Button(top, text="Abrir carpeta PDFs", command=self._pdf_execute_open_folder)
        self.pdf_execute_open_folder_button.pack(side="right", padx=(8, 0))

        self.pdf_execute_counts = tk.StringVar(value="Query 0/8 · Encontrados 0 · Descargados 0 · Válidos 0 · Rechazados 0")
        ttk.Label(box, textvariable=self.pdf_execute_counts).pack(anchor="w", fill="x", pady=(5, 0))

        progress_row = ttk.Frame(box)
        progress_row.pack(fill="x", pady=(5, 0))
        self.pdf_execute_progress_bar = ttk.Progressbar(progress_row, maximum=100, mode="determinate")
        self.pdf_execute_progress_bar.pack(side="left", fill="x", expand=True)
        self.pdf_execute_progress_value = tk.StringVar(value="0%")
        ttk.Label(progress_row, textvariable=self.pdf_execute_progress_value, width=7).pack(side="left", padx=(8, 0))

        self.pdf_execute_folder = tk.StringVar(value="Carpeta: pendiente")
        ttk.Label(box, textvariable=self.pdf_execute_folder, wraplength=900, justify="left").pack(anchor="w", fill="x", pady=(5, 0))
        self.pdf_execute_summary = tk.StringVar(value="Resumen PDF: pendiente")
        ttk.Label(box, textvariable=self.pdf_execute_summary, wraplength=900, justify="left").pack(anchor="w", fill="x", pady=(3, 0))
        return result

    def _pdf_execute_product_label(self, index: int) -> str:
        return self._pdf_identifier_for_index(index)

    def _pdf_execute_summary_text(self) -> str:
        results = getattr(self, "_pdf_execute_results", {}) or {}
        if not results:
            return "Resumen PDF: pendiente"
        parts = [f"{self._pdf_execute_product_label(index)}: {results[index]}" for index in sorted(results)]
        return "Resumen PDF · " + " | ".join(parts)

    def _update_pdf_execute_panel(self, index: int, event: dict) -> PdfExecuteRuntimeState:
        states = getattr(self, "_pdf_execute_states", None)
        if states is None:
            states = {}
            self._pdf_execute_states = states
        state = states.setdefault(index, PdfExecuteRuntimeState())
        state.apply(event)
        self._pdf_execute_active_index = index

        if str(event.get("type") or "") == "final_result" and not event.get("error"):
            payload = event.get("result")
            if payload is not None:
                results = getattr(self, "_pdf_execute_results", None)
                if results is None:
                    results = {}
                    self._pdf_execute_results = results
                results[index] = int(getattr(payload, "validated_count", state.validated) or 0)

        total = max(1, len(list(getattr(self, "product_rows", []) or [])))
        label = self._pdf_execute_product_label(index)
        folder = self._pdf_folder_for_index(index)
        status_text = f"PDF · Producto {index + 1}/{total} · {label} · {state.status}"
        counts_text = (
            f"Query {state.query_position}/{state.query_limit} · Encontrados {state.found} · "
            f"Descargados {state.downloaded} · Válidos {state.validated} · Rechazados {state.rejected}"
        )

        status_var = self.__dict__.get("pdf_execute_status")
        counts_var = self.__dict__.get("pdf_execute_counts")
        progress_var = self.__dict__.get("pdf_execute_progress_value")
        folder_var = self.__dict__.get("pdf_execute_folder")
        summary_var = self.__dict__.get("pdf_execute_summary")
        progress_bar = self.__dict__.get("pdf_execute_progress_bar")
        if status_var is not None:
            status_var.set(status_text)
        if counts_var is not None:
            counts_var.set(counts_text)
        if progress_var is not None:
            progress_var.set(f"{state.progress}%")
        if folder_var is not None:
            folder_var.set(f"Carpeta: {folder}")
        if summary_var is not None:
            summary_var.set(self._pdf_execute_summary_text())
        if progress_bar is not None:
            progress_bar["value"] = state.progress
        return state

    def _emit_pdf_global(self, text: str) -> None:
        emit = self.__dict__.get("emit")
        if not callable(emit):
            emit_fn = getattr(type(self), "emit", None)
            if callable(emit_fn) and "tk" in self.__dict__:
                emit = lambda line, fn=emit_fn: fn(self, line)
        if callable(emit):
            emit(f"[PDF REVIEW] {text}")

    def _pdf_progress_stage(self, text: str) -> None:
        # Unit/state-contract clients may inject a callback directly without
        # initializing Tk. Prefer that explicit callback. Only call the inherited
        # Tk implementation when the real desktop root is initialized.
        stage = self.__dict__.get("_excel_progress_stage")
        if callable(stage):
            stage(text)
            return
        if "tk" not in self.__dict__:
            return
        stage_fn = getattr(type(self), "_excel_progress_stage", None)
        if callable(stage_fn):
            stage_fn(self, text)

    def run(self):
        rows = list(getattr(self, "product_rows", []) or [])
        mode = self.__dict__.get("pdf_review_mode")
        enabled = self.__dict__.get("use_pdf_evidence")
        reviewed_mode = bool(mode is not None and mode.get() == "reviewed")
        pdf_enabled = bool(enabled is not None and enabled.get())
        missing = review_gate_missing_indices(
            total_products=len(rows),
            reviewed_mode=reviewed_mode,
            pdf_enabled=pdf_enabled,
            enforced_indices=getattr(self, "_pdf_review_enforced", set()),
        )
        if missing:
            first = missing[0]
            pending = ", ".join(str(index + 1) for index in missing)
            self._emit_pdf_global(
                f"Ejecución pausada antes del scraping: buscando/esperando revisión PDF del producto "
                f"{first + 1}/{len(rows)}. Pendientes: {pending}."
            )
            self._pdf_progress_stage(f"PDF · buscando documentos · producto {first + 1}/{len(rows)}")
        return super().run()

    def _pdf_review_search(self):
        label = self._pdf_review_identifier()
        folder = self._pdf_review_root() / "pdf_review" / label
        folder.mkdir(parents=True, exist_ok=True)
        try:
            index = self._pdf_review_product_index()
        except Exception:
            index = None
        if index is not None:
            states = getattr(self, "_pdf_execute_states", None)
            if states is None:
                states = {}
                self._pdf_execute_states = states
            states[index] = PdfExecuteRuntimeState()
            self._pdf_execute_active_index = index
            self._update_pdf_execute_panel(index, {"type": "stage", "stage": "IDENTITY"})
        self._emit_pdf_global(f"Inicio búsqueda PDF · producto={label} · carpeta={folder}")
        self._pdf_progress_stage(f"PDF · buscando documentos · {label}")
        return super()._pdf_review_search()

    def _apply_pdf_live_event(self, index: int, event: dict):
        self._update_pdf_execute_panel(index, event)
        kind = str(event.get("type") or "")
        if kind == "log":
            message = str(event.get("message") or "Buscando PDFs…")
            self._emit_pdf_global(message)
        elif kind == "query":
            position = int(event.get("position") or 0)
            limit = int(event.get("limit") or 0)
            query = str(event.get("query") or "").strip()
            self._emit_pdf_global(f"QUERY {position}/{limit} · {query}")
            self._pdf_progress_stage(f"PDF · query {position}/{limit} · {query}")
        elif kind == "identity":
            brand = str(event.get("brand") or "-")
            model = str(event.get("model") or "-")
            domain = str(event.get("official_domain") or "-")
            status = str(event.get("status") or "-")
            self._emit_pdf_global(f"IDENTIDAD · brand={brand} · model={model} · dominio={domain} · status={status}")
            self._pdf_progress_stage(f"PDF · identidad {brand} · {model}")
        elif kind == "candidate":
            title = str(event.get("title") or "documento").strip()
            url = str(event.get("url") or "").strip()
            self._emit_pdf_global(f"ENCONTRADO · {title} · {url}")
            self._pdf_progress_stage("PDF · candidatos encontrados")
        elif kind == "download":
            status = str(event.get("status") or "").upper()
            url = str(event.get("url") or "").strip()
            local_path = str(event.get("local_path") or "").strip()
            if status == "FINISHED":
                self._emit_pdf_global(f"DESCARGADO · {local_path or url} · url={url}")
                self._pdf_progress_stage("PDF · descarga completada")
            else:
                self._emit_pdf_global(f"DESCARGANDO · {url}")
                self._pdf_progress_stage("PDF · descargando")
        elif kind == "validated":
            row = event.get("row")
            candidate = getattr(row, "candidate", None)
            inspection = getattr(row, "inspection", None)
            url = str(event.get("url") or getattr(candidate, "url", "") or "").strip()
            title = str(getattr(candidate, "title", "") or Path(url).name or "documento").strip()
            local_path = str(getattr(inspection, "local_path", "") or "").strip()
            pages = int(event.get("pages") or getattr(inspection, "page_count", 0) or 0)
            filename = Path(local_path).name if local_path else title
            self._emit_pdf_global(
                f"ACEPTADO · {filename} · pages={pages} · archivo={local_path or '-'} · url={url}"
            )
            self._pdf_progress_stage("PDF · evidencia aceptada")
        elif kind == "rejected":
            url = str(event.get("url") or "").strip()
            reason = str(event.get("reason") or event.get("error") or "SIN_MOTIVO").strip()
            pages = int(event.get("pages") or 0)
            self._emit_pdf_global(f"RECHAZADO · motivo={reason} · pages={pages} · url={url}")
            self._pdf_progress_stage("PDF · candidato rechazado")
        elif kind == "duplicate":
            url = str(event.get("url") or "").strip()
            final_url = str(event.get("final_url") or "").strip()
            self._emit_pdf_global(f"DUPLICADO · {url} · final={final_url or '-'}")
            self._pdf_progress_stage("PDF · candidato duplicado")

        result = super()._apply_pdf_live_event(index, event)

        if kind == "final_result":
            payload = event.get("result")
            error = event.get("error")
            folder = self._pdf_folder_for_index(index)
            if error:
                self._emit_pdf_global(f"ERROR · {error} · carpeta={folder}")
                self._pdf_progress_stage("PDF · error")
            elif payload is not None:
                self._emit_pdf_global(
                    f"FIN · descubiertos={getattr(payload, 'discovered_count', 0)} · "
                    f"descargados={getattr(payload, 'downloaded_count', 0)} · "
                    f"validados={getattr(payload, 'validated_count', 0)} · "
                    f"rechazados={getattr(payload, 'rejected_count', 0)} · carpeta={folder}"
                )
                self._pdf_progress_stage("PDF · revisión lista; selecciona y confirma")
        return result