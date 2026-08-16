from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from . import pdf_desktop as pdf_desktop_module
from .managed_desktop import App as ManagedApp
from .pdf_review import PdfInspection, PdfReviewCandidate, discover_review_candidates, inspect_pdf_candidate
from .pdf_review_batch import run_batch_with_review, set_desktop_review_plan


# The inherited Excel runner resolves this module global at execution time. Replace only
# the call boundary; the underlying batch implementation remains unchanged.
pdf_desktop_module.run_batch = run_batch_with_review


class App(ManagedApp):
    """Final additive shell with a user-controlled PDF evidence review workspace."""

    def __init__(self):
        self._pdf_review_candidates: dict[int, list[PdfReviewCandidate]] = {}
        self._pdf_review_inspections: dict[int, dict[str, PdfInspection]] = {}
        self._pdf_review_selected: dict[int, set[str]] = {}
        self._pdf_review_enforced: set[int] = set()
        self._pdf_review_photo = None
        super().__init__()
        self._install_pdf_review_workspace()
        self._pdf_review_refresh_products()

    def _install_pdf_review_workspace(self):
        self.pdf_review_tab = ttk.Frame(self.notebook, style="Page.TFrame", padding=(12, 12))
        self.notebook.add(self.pdf_review_tab, text="Revisión PDF")
        self._workspace_tabs["pdf_review"] = self.pdf_review_tab

        nav_parent = self._nav_buttons["products"].master
        self._pdf_review_nav_button = ttk.Button(
            nav_parent,
            text="▧   Revisión PDF",
            style="Nav.TButton",
            command=lambda: self._show_workspace("pdf_review"),
        )
        before = self._nav_buttons.get("audit")
        pack_kwargs = {"fill": "x", "padx": 10, "pady": (2, 2)}
        if before is not None:
            pack_kwargs["before"] = before
        self._pdf_review_nav_button.pack(**pack_kwargs)
        self._nav_buttons["pdf_review"] = self._pdf_review_nav_button

        header = ttk.Frame(self.pdf_review_tab, style="Page.TFrame")
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Revisión de documentos PDF", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="Busca documentos técnicos, revisa la vista previa y decide cuáles pueden aportar evidencia. La revisión no consume OCR ni Mistral.",
            wraplength=1050,
        ).pack(anchor="w", pady=(2, 0))

        controls = ttk.LabelFrame(self.pdf_review_tab, text="Producto y acciones", style="Card.TLabelframe", padding=8)
        controls.pack(fill="x", pady=(0, 10))
        ttk.Label(controls, text="Producto").pack(side="left")
        self.pdf_review_product = tk.StringVar()
        self.pdf_review_product_box = ttk.Combobox(controls, textvariable=self.pdf_review_product, state="readonly", width=42)
        self.pdf_review_product_box.pack(side="left", padx=(8, 10))
        self.pdf_review_product_box.bind("<<ComboboxSelected>>", lambda _event: self._pdf_review_refresh_tree())
        self.pdf_review_search_button = ttk.Button(controls, text="Buscar PDFs", style="Primary.TButton", command=self._pdf_review_search)
        self.pdf_review_search_button.pack(side="left")
        ttk.Button(controls, text="Usar / quitar", command=self._pdf_review_toggle_use).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Confirmar selección", command=self._pdf_review_confirm).pack(side="left", padx=(8, 0))
        self.pdf_review_status = tk.StringVar(value="Analiza un Excel y luego busca PDFs para el producto seleccionado.")
        ttk.Label(controls, textvariable=self.pdf_review_status, wraplength=430, justify="left").pack(side="right", padx=(12, 0))

        body = ttk.Panedwindow(self.pdf_review_tab, orient="horizontal")
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="PDFs encontrados", style="Card.TLabelframe", padding=6)
        right = ttk.LabelFrame(body, text="Vista previa y evaluación", style="Card.TLabelframe", padding=8)
        body.add(left, weight=3)
        body.add(right, weight=2)

        columns = ("use", "score", "type", "identity", "text", "ocr", "source")
        self.pdf_review_tree = ttk.Treeview(left, columns=columns, show="headings", style="Modern.Treeview", height=18)
        headings = {
            "use": "Usar",
            "score": "Score",
            "type": "Tipo",
            "identity": "Identidad",
            "text": "Texto",
            "ocr": "OCR",
            "source": "Fuente",
        }
        widths = {"use": 55, "score": 60, "type": 105, "identity": 125, "text": 90, "ocr": 95, "source": 260}
        for col in columns:
            self.pdf_review_tree.heading(col, text=headings[col])
            self.pdf_review_tree.column(col, width=widths[col], anchor="w")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.pdf_review_tree.yview)
        self.pdf_review_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.pdf_review_tree.pack(side="left", fill="both", expand=True)
        self.pdf_review_tree.bind("<<TreeviewSelect>>", lambda _event: self._pdf_review_inspect_selected())

        preview_frame = ttk.Frame(right, style="Card.TFrame")
        preview_frame.pack(fill="both", expand=True)
        self.pdf_review_preview = ttk.Label(
            preview_frame,
            text="Selecciona un PDF para descargarlo y mostrar la primera página.",
            anchor="center",
            justify="center",
        )
        self.pdf_review_preview.pack(fill="both", expand=True)
        self.pdf_review_detail = tk.StringVar(value="Todavía no hay un documento inspeccionado.")
        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=8)
        ttk.Label(right, textvariable=self.pdf_review_detail, wraplength=500, justify="left").pack(fill="x")

    def _show_workspace(self, key: str):
        super()._show_workspace(key)
        if key == "pdf_review":
            self._pdf_review_refresh_products()
            if hasattr(self, "_page_title"):
                self._page_title.set("Revisión PDF")
                self._page_subtitle.set("Selecciona y audita los documentos que podrán aportar evidencia técnica.")

    def _apply_analysis_result(self, data: dict):
        super()._apply_analysis_result(data)
        self._pdf_review_refresh_products()

    def _pdf_review_refresh_products(self):
        box = getattr(self, "pdf_review_product_box", None)
        if box is None:
            return
        current = box.current()
        labels = []
        for index, row in enumerate(list(getattr(self, "product_rows", []) or [])):
            identity = self._identity_for_index(index)
            value = None
            if identity is not None:
                value = identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name
            labels.append(str(value or row.get("model") or row.get("product_name") or f"Producto {index + 1}"))
        box.configure(values=labels)
        if labels:
            box.current(current if 0 <= current < len(labels) else 0)
            self.pdf_review_status.set(f"{len(labels)} producto(s) disponibles para revisión PDF.")
        else:
            self.pdf_review_product.set("")
            self.pdf_review_status.set("Analiza un Excel para cargar productos.")
        self._pdf_review_refresh_tree()

    def _pdf_review_product_index(self) -> int | None:
        box = getattr(self, "pdf_review_product_box", None)
        if box is None:
            return None
        index = int(box.current())
        return index if index >= 0 else None

    def _pdf_review_search(self):
        index = self._pdf_review_product_index()
        if index is None:
            messagebox.showinfo("Revisión PDF", "Selecciona un producto primero.")
            return
        identity = self._identity_for_index(index)
        if identity is None:
            messagebox.showerror("Revisión PDF", "El producto no tiene identidad válida.")
            return

        self.pdf_review_search_button.configure(state="disabled")
        self.pdf_review_status.set("Buscando PDFs técnicos…")
        self._pdf_review_selected[index] = set()
        self._pdf_review_enforced.discard(index)
        self._pdf_review_candidates[index] = []
        self._pdf_review_inspections[index] = {}
        self._pdf_review_refresh_tree()

        def work():
            try:
                rows = discover_review_candidates(identity, limit=10)
                self.after(0, lambda: self._pdf_review_search_done(index, rows, None))
            except Exception as exc:
                self.after(0, lambda: self._pdf_review_search_done(index, [], f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=work, daemon=True).start()

    def _pdf_review_search_done(self, index: int, rows: list[PdfReviewCandidate], error: str | None):
        self.pdf_review_search_button.configure(state="normal")
        if error:
            self.pdf_review_status.set(f"Error buscando PDFs: {error}")
            return
        self._pdf_review_candidates[index] = list(rows)
        self.pdf_review_status.set(f"Se encontraron {len(rows)} PDF(s). Selecciona uno para previsualizar y validar.")
        self._pdf_review_refresh_tree()
        if rows and self._pdf_review_product_index() == index:
            first = self.pdf_review_tree.get_children()
            if first:
                self.pdf_review_tree.selection_set(first[0])
                self.pdf_review_tree.focus(first[0])
                self._pdf_review_inspect_selected()

    def _pdf_review_refresh_tree(self):
        tree = getattr(self, "pdf_review_tree", None)
        if tree is None:
            return
        for item in tree.get_children():
            tree.delete(item)
        index = self._pdf_review_product_index()
        if index is None:
            return
        rows = self._pdf_review_candidates.get(index, [])
        inspections = self._pdf_review_inspections.get(index, {})
        selected = self._pdf_review_selected.get(index, set())
        for pos, row in enumerate(rows):
            inspection = inspections.get(row.url)
            identity = "Sin revisar"
            text_state = "—"
            ocr_state = "—"
            score = row.review_score
            if inspection is not None:
                if inspection.identity_accepted:
                    identity = "ACEPTADA"
                elif inspection.identity_pending_ocr:
                    identity = "PENDIENTE OCR"
                else:
                    identity = "RECHAZADA"
                text_state = f"{inspection.native_text_chars} chars"
                ocr_state = "Recomendado" if inspection.ocr_recommended else "No necesario"
                score = inspection.review_score
            tree.insert(
                "",
                "end",
                iid=str(pos),
                values=("✓" if row.url in selected else "", score, row.document_type, identity, text_state, ocr_state, row.host),
            )

    def _pdf_review_selected_candidate(self) -> tuple[int, PdfReviewCandidate] | None:
        index = self._pdf_review_product_index()
        selected = self.pdf_review_tree.selection() if hasattr(self, "pdf_review_tree") else ()
        if index is None or not selected:
            return None
        try:
            pos = int(selected[0])
        except (TypeError, ValueError):
            return None
        rows = self._pdf_review_candidates.get(index, [])
        if pos < 0 or pos >= len(rows):
            return None
        return index, rows[pos]

    def _pdf_review_inspect_selected(self):
        pair = self._pdf_review_selected_candidate()
        if pair is None:
            return
        index, candidate = pair
        inspection = self._pdf_review_inspections.get(index, {}).get(candidate.url)
        if inspection is not None:
            self._pdf_review_show_inspection(inspection)
            return
        identity = self._identity_for_index(index)
        if identity is None:
            return
        self.pdf_review_status.set("Descargando e inspeccionando PDF…")
        out_var = getattr(self, "out", None)
        output = str(out_var.get() if out_var is not None else "").strip()
        root = Path(output) if output else (Path.home() / "ProductIntelligence_Output")
        label = re.sub(r"[^A-Za-z0-9._-]+", "_", str(identity.mpn or identity.model or index))
        cache_dir = root / "pdf_review" / label

        def work():
            try:
                result = inspect_pdf_candidate(
                    identity,
                    candidate.url,
                    cache_dir,
                    document_type=candidate.document_type,
                    likely_official=candidate.likely_official,
                    discovery_score=candidate.discovery_score,
                )
                self.after(0, lambda: self._pdf_review_inspection_done(index, candidate.url, result, None))
            except Exception as exc:
                self.after(0, lambda: self._pdf_review_inspection_done(index, candidate.url, None, f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=work, daemon=True).start()

    def _pdf_review_inspection_done(self, index: int, url: str, result: PdfInspection | None, error: str | None):
        if error or result is None:
            self.pdf_review_status.set(f"No se pudo inspeccionar el PDF: {error or 'error desconocido'}")
            self.pdf_review_detail.set(f"ERROR DE INSPECCIÓN\nURL: {url}\n{error or ''}")
            return
        self._pdf_review_inspections.setdefault(index, {})[url] = result
        if not result.identity_accepted and not result.identity_pending_ocr:
            self._pdf_review_selected.setdefault(index, set()).discard(url)
        self._pdf_review_refresh_tree()
        self._pdf_review_show_inspection(result)
        if result.identity_accepted:
            state = "identidad validada"
        elif result.identity_pending_ocr:
            state = "identidad pendiente de OCR; todavía no es evidencia aceptada"
        else:
            state = f"rechazado: {result.identity_reason}"
        self.pdf_review_status.set(f"PDF inspeccionado · {state}.")

    def _pdf_review_show_inspection(self, inspection: PdfInspection):
        try:
            image = Image.open(BytesIO(inspection.preview_png))
            image.thumbnail((520, 620), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self._pdf_review_photo = photo
            self.pdf_review_preview.configure(image=photo, text="")
        except Exception:
            self._pdf_review_photo = None
            self.pdf_review_preview.configure(image="", text="No se pudo renderizar la vista previa, pero la evaluación textual sigue disponible.")

        if inspection.identity_accepted:
            identity_label = "ACEPTADA"
        elif inspection.identity_pending_ocr:
            identity_label = "PENDIENTE OCR"
        else:
            identity_label = "RECHAZADA"
        ocr_label = "Sí, durante la ejecución si OCR está habilitado" if inspection.ocr_recommended else "No; el texto nativo es suficiente"
        pending_note = (
            "\nIMPORTANTE: pendiente OCR no significa evidencia aceptada. Si lo seleccionas, OCR deberá confirmar la identidad durante la ejecución."
            if inspection.identity_pending_ocr else ""
        )
        self.pdf_review_detail.set(
            f"Score de revisión: {inspection.review_score}/100\n"
            f"Identidad: {identity_label} · {inspection.identity_reason} · confianza {inspection.identity_confidence:.2f}\n"
            f"Páginas: {inspection.page_count} · texto nativo: {inspection.native_text_chars} caracteres\n"
            f"OCR recomendado: {ocr_label}\n"
            f"Archivo local: {inspection.local_path}\n"
            f"URL: {inspection.final_url}{pending_note}\n\n"
            "La vista previa no ejecuta OCR ni Mistral. Esos proveedores solo pueden intervenir después, durante la ejecución normal."
        )

    def _pdf_review_toggle_use(self):
        pair = self._pdf_review_selected_candidate()
        if pair is None:
            messagebox.showinfo("Revisión PDF", "Selecciona un PDF primero.")
            return
        index, candidate = pair
        inspection = self._pdf_review_inspections.get(index, {}).get(candidate.url)
        if inspection is None:
            messagebox.showinfo("Revisión PDF", "Primero deja que termine la inspección y la vista previa de este PDF.")
            self._pdf_review_inspect_selected()
            return
        if not inspection.identity_accepted and not inspection.identity_pending_ocr:
            messagebox.showwarning("Revisión PDF", "Este PDF fue rechazado por identidad y no puede usarse como evidencia.")
            return
        selected = self._pdf_review_selected.setdefault(index, set())
        if candidate.url in selected:
            selected.remove(candidate.url)
        else:
            selected.add(candidate.url)
        self._pdf_review_enforced.discard(index)
        self._pdf_review_refresh_tree()
        note = " Los pendientes OCR todavía deberán validar identidad durante la ejecución." if inspection.identity_pending_ocr else ""
        self.pdf_review_status.set(f"Selección pendiente de confirmar: {len(selected)} PDF(s).{note}")

    def _pdf_review_confirm(self):
        index = self._pdf_review_product_index()
        if index is None:
            messagebox.showinfo("Revisión PDF", "Selecciona un producto primero.")
            return
        selected = self._pdf_review_selected.setdefault(index, set())
        self._pdf_review_enforced.add(index)
        self.pdf_review_status.set(
            f"Selección confirmada: {len(selected)} PDF(s). En el próximo Scraping Excel solo estos PDFs podrán aportar evidencia para este producto."
        )

    def run(self):
        rows = list(getattr(self, "product_rows", []) or [])
        reviewed = [sorted(self._pdf_review_selected.get(index, set())) for index in range(len(rows))]
        flags = [index in self._pdf_review_enforced for index in range(len(rows))]
        set_desktop_review_plan(reviewed, flags)
        return super().run()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
