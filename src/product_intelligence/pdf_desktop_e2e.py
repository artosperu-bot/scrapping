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
        self._emit_pdf_global(f"Inicio búsqueda PDF · producto={label} · carpeta={folder}")
        self._pdf_progress_stage(f"PDF · buscando documentos · {label}")
        return super()._pdf_review_search()

    def _apply_pdf_live_event(self, index: int, event: dict):
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