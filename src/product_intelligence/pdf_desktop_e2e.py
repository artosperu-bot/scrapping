from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
from tkinter import messagebox, ttk

from .real_pdf_review_shell import review_gate_missing_indices


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

    def _pdf_review_identifier(self) -> str:
        index = None
        try:
            index = self._pdf_review_product_index()
        except Exception:
            pass
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
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value)

    def _pdf_review_current_folder(self) -> Path:
        root = self._pdf_review_root()
        label = self._pdf_review_identifier()
        review = root / "pdf_review" / label
        evidence = root / "pdf_evidence" / label
        if review.exists():
            return review
        if evidence.exists():
            return evidence
        review.mkdir(parents=True, exist_ok=True)
        return review

    def _pdf_review_open_folder(self):
        folder = self._pdf_review_current_folder()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror("Revisión PDF", f"No se pudo abrir la carpeta:\n{folder}\n\n{type(exc).__name__}: {exc}")
            return
        status = self.__dict__.get("pdf_review_status")
        if status is not None:
            status.set(f"Carpeta PDFs: {folder}")

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

    def _emit_pdf_global(self, text: str) -> None:
        emit = self.__dict__.get("emit")
        if not callable(emit):
            emit_fn = getattr(type(self), "emit", None)
            if callable(emit_fn):
                emit = lambda line, fn=emit_fn: fn(self, line)
        if callable(emit):
            emit(f"[PDF REVIEW] {text}")

    def _pdf_progress_stage(self, text: str) -> None:
        stage = self.__dict__.get("_excel_progress_stage")
        if not callable(stage):
            stage_fn = getattr(type(self), "_excel_progress_stage", None)
            if callable(stage_fn):
                stage = lambda line, fn=stage_fn: fn(self, line)
        if callable(stage):
            stage(text)

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
        self._emit_pdf_global(f"Inicio búsqueda PDF · producto={label} · carpeta={folder}")
        self._pdf_progress_stage(f"PDF · buscando documentos · {label}")
        return super()._pdf_review_search()

    def _apply_pdf_live_event(self, index: int, event: dict):
        kind = str(event.get("type") or "")
        if kind == "log":
            message = str(event.get("message") or "Buscando PDFs…")
            self._emit_pdf_global(message)
        elif kind == "candidate":
            self._pdf_progress_stage("PDF · candidatos encontrados")
        elif kind == "download":
            status = str(event.get("status") or "").upper()
            self._pdf_progress_stage("PDF · descargando" if status != "FINISHED" else "PDF · descarga completada")
        elif kind == "validated":
            self._pdf_progress_stage("PDF · validando evidencia")
        elif kind == "rejected":
            self._pdf_progress_stage("PDF · filtrando candidatos")

        result = super()._apply_pdf_live_event(index, event)

        if kind == "final_result":
            payload = event.get("result")
            error = event.get("error")
            folder = self._pdf_review_root() / "pdf_review" / self._pdf_review_identifier()
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
