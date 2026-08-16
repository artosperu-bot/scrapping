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
from .pdf_review import PdfInspection, PdfReviewCandidate, discover_review_candidates, inspect_pdf_candidate, render_pdf_page
from .pdf_review_batch import run_batch_with_review, set_desktop_review_plan


pdf_desktop_module.run_batch = run_batch_with_review


class App(ManagedApp):
    """Final additive shell with precision-first, user-controlled PDF evidence review."""

    def __init__(self):
        self._pdf_review_candidates: dict[int, list[PdfReviewCandidate]] = {}
        self._pdf_review_inspections: dict[int, dict[str, PdfInspection]] = {}
        self._pdf_review_selected: dict[int, set[str]] = {}
        self._pdf_review_enforced: set[int] = set()
        self._pdf_review_photo = None
        self._pdf_review_current_url: str | None = None
        self._pdf_review_page_index = 0
        self._pdf_review_zoom = 1.0
        self._pdf_review_fit_mode = "width"
        self._pdf_review_render_cache: dict[tuple[str, int, int, str], bytes] = {}
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
            text="Busca documentos del producto exacto, revísalos página por página y decide cuáles pueden aportar evidencia. El preview no consume OCR ni Mistral.",
            wraplength=1120,
        ).pack(anchor="w", pady=(2, 0))

        controls = ttk.LabelFrame(self.pdf_review_tab, text="Producto, modo y acciones", style="Card.TLabelframe", padding=8)
        controls.pack(fill="x", pady=(0, 10))
        ttk.Label(controls, text="Producto").pack(side="left")
        self.pdf_review_product = tk.StringVar()
        self.pdf_review_product_box = ttk.Combobox(controls, textvariable=self.pdf_review_product, state="readonly", width=34)
        self.pdf_review_product_box.pack(side="left", padx=(8, 12))
        self.pdf_review_product_box.bind("<<ComboboxSelected>>", lambda _event: self._pdf_review_refresh_tree())

        self.pdf_review_mode = tk.StringVar(value="reviewed")
        ttk.Radiobutton(controls, text="Revisar antes de usar", variable=self.pdf_review_mode, value="reviewed", command=self._pdf_review_mode_changed).pack(side="left")
        ttk.Radiobutton(controls, text="Automático", variable=self.pdf_review_mode, value="automatic", command=self._pdf_review_mode_changed).pack(side="left", padx=(6, 12))

        self.pdf_review_search_button = ttk.Button(controls, text="Buscar PDFs", style="Primary.TButton", command=self._pdf_review_search)
        self.pdf_review_search_button.pack(side="left")
        ttk.Button(controls, text="Usar / quitar", command=self._pdf_review_toggle_use).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Confirmar selección", command=self._pdf_review_confirm).pack(side="left", padx=(8, 0))
        self.pdf_review_status = tk.StringVar(value="Analiza un Excel y luego busca PDFs para el producto seleccionado.")
        ttk.Label(controls, textvariable=self.pdf_review_status, wraplength=360, justify="left").pack(side="right", padx=(12, 0))

        body = ttk.Panedwindow(self.pdf_review_tab, orient="horizontal")
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="PDFs relevantes", style="Card.TLabelframe", padding=6)
        right = ttk.LabelFrame(body, text="Vista previa y evaluación", style="Card.TLabelframe", padding=8)
        body.add(left, weight=3)
        body.add(right, weight=4)

        columns = ("use", "score", "document", "type", "identity", "authority", "pages", "text", "ocr", "source")
        self.pdf_review_tree = ttk.Treeview(left, columns=columns, show="headings", style="Modern.Treeview", height=18)
        headings = {
            "use": "Usar", "score": "Score", "document": "Documento", "type": "Tipo", "identity": "Identidad",
            "authority": "Autoridad", "pages": "Págs.", "text": "Texto", "ocr": "OCR", "source": "Fuente",
        }
        widths = {"use": 48, "score": 55, "document": 210, "type": 95, "identity": 125, "authority": 105, "pages": 48, "text": 80, "ocr": 90, "source": 160}
        for col in columns:
            self.pdf_review_tree.heading(col, text=headings[col])
            self.pdf_review_tree.column(col, width=widths[col], anchor="w")
        tree_y = ttk.Scrollbar(left, orient="vertical", command=self.pdf_review_tree.yview)
        tree_x = ttk.Scrollbar(left, orient="horizontal", command=self.pdf_review_tree.xview)
        self.pdf_review_tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)
        tree_y.pack(side="right", fill="y")
        tree_x.pack(side="bottom", fill="x")
        self.pdf_review_tree.pack(side="left", fill="both", expand=True)
        self.pdf_review_tree.bind("<<TreeviewSelect>>", lambda _event: self._pdf_review_inspect_selected())

        reader_bar = ttk.Frame(right, style="Card.TFrame")
        reader_bar.pack(fill="x", pady=(0, 6))
        ttk.Button(reader_bar, text="Primera", command=lambda: self._pdf_review_go_page("first")).pack(side="left")
        ttk.Button(reader_bar, text="Anterior", command=lambda: self._pdf_review_go_page("prev")).pack(side="left", padx=(4, 0))
        self.pdf_review_page_label = tk.StringVar(value="Página — / —")
        ttk.Label(reader_bar, textvariable=self.pdf_review_page_label, width=16, anchor="center").pack(side="left", padx=8)
        ttk.Button(reader_bar, text="Siguiente", command=lambda: self._pdf_review_go_page("next")).pack(side="left")
        ttk.Button(reader_bar, text="Última", command=lambda: self._pdf_review_go_page("last")).pack(side="left", padx=(4, 10))
        ttk.Button(reader_bar, text="Zoom -", command=lambda: self._pdf_review_change_zoom(-0.25)).pack(side="left")
        self.pdf_review_zoom_label = tk.StringVar(value="100%")
        ttk.Label(reader_bar, textvariable=self.pdf_review_zoom_label, width=7, anchor="center").pack(side="left")
        ttk.Button(reader_bar, text="Zoom +", command=lambda: self._pdf_review_change_zoom(0.25)).pack(side="left")
        ttk.Button(reader_bar, text="Ajustar ancho", command=lambda: self._pdf_review_set_fit("width")).pack(side="left", padx=(10, 0))
        ttk.Button(reader_bar, text="Ajustar página", command=lambda: self._pdf_review_set_fit("page")).pack(side="left", padx=(4, 0))

        preview_frame = ttk.Frame(right, style="Card.TFrame")
        preview_frame.pack(fill="both", expand=True)
        self.pdf_review_canvas = tk.Canvas(preview_frame, highlightthickness=0, background="#202020")
        preview_y = ttk.Scrollbar(preview_frame, orient="vertical", command=self.pdf_review_canvas.yview)
        preview_x = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.pdf_review_canvas.xview)
        self.pdf_review_canvas.configure(yscrollcommand=preview_y.set, xscrollcommand=preview_x.set)
        preview_y.pack(side="right", fill="y")
        preview_x.pack(side="bottom", fill="x")
        self.pdf_review_canvas.pack(side="left", fill="both", expand=True)
        self.pdf_review_canvas.create_text(260, 220, text="Selecciona un PDF para abrir la vista previa.", fill="white", tags=("placeholder",))
        self.pdf_review_canvas.bind("<MouseWheel>", self._pdf_review_mousewheel)
        self.pdf_review_canvas.bind("<Control-MouseWheel>", self._pdf_review_ctrl_mousewheel)
        self.pdf_review_canvas.bind("<Configure>", lambda _event: self._pdf_review_rerender_if_fit())

        self.pdf_review_detail = tk.StringVar(value="Todavía no hay un documento inspeccionado.")
        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=8)
        ttk.Label(right, textvariable=self.pdf_review_detail, wraplength=650, justify="left").pack(fill="x")

    def _pdf_review_mode_changed(self):
        if self.pdf_review_mode.get() == "automatic":
            self.pdf_review_status.set("Modo Automático: el batch conserva el comportamiento PDF automático actual.")
        else:
            self.pdf_review_status.set("Modo Revisar antes de usar: el batch respetará solo la selección que confirmes.")

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
        self.pdf_review_status.set("Buscando y filtrando PDFs del producto exacto…")
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
        self.pdf_review_status.set(f"{len(rows)} PDF(s) relevantes listos para revisar. Nada se usa hasta confirmar selección en modo revisado.")
        self._pdf_review_refresh_tree()
        if rows and self._pdf_review_product_index() == index:
            first = self.pdf_review_tree.get_children()
            if first:
                self.pdf_review_tree.selection_set(first[0])
                self.pdf_review_tree.focus(first[0])

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
            identity = row.identity_status or "Sin revisar"
            text_state = "—"
            ocr_state = "—"
            pages = "—"
            score = row.review_score
            if inspection is not None:
                if inspection.identity_provenance_bound:
                    identity = "PROVENANCE_BOUND"
                elif inspection.identity_accepted:
                    identity = "ACEPTADA"
                elif inspection.identity_pending_ocr:
                    identity = "PENDIENTE OCR"
                else:
                    identity = "RECHAZADA"
                text_state = f"{inspection.native_text_chars} chars"
                ocr_state = "Recomendado" if inspection.ocr_recommended else "No necesario"
                pages = str(inspection.page_count)
                score = inspection.review_score
            tree.insert(
                "", "end", iid=str(pos),
                values=("✓" if row.url in selected else "", score, row.title or Path(row.url).name, row.document_type,
                        identity, row.authority_label, pages, text_state, ocr_state, row.host),
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
            self._pdf_review_open_inspection(inspection)
            return
        identity = self._identity_for_index(index)
        if identity is None:
            return
        self.pdf_review_status.set("Descargando temporalmente el PDF para vista previa…")
        out_var = getattr(self, "out", None)
        output = str(out_var.get() if out_var is not None else "").strip()
        root = Path(output) if output else (Path.home() / "ProductIntelligence_Output")
        label = re.sub(r"[^A-Za-z0-9._-]+", "_", str(identity.mpn or identity.model or index))
        cache_dir = root / "pdf_review" / label

        def work():
            try:
                result = inspect_pdf_candidate(
                    identity, candidate.url, cache_dir,
                    document_type=candidate.document_type,
                    likely_official=candidate.likely_official,
                    discovery_score=candidate.discovery_score,
                    provenance=candidate.provenance,
                    identity_score=candidate.identity_score,
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
        self._pdf_review_open_inspection(result)
        if result.identity_provenance_bound:
            state = "identidad enlazada de forma segura desde la landing validada"
        elif result.identity_accepted:
            state = "identidad validada"
        elif result.identity_pending_ocr:
            state = "identidad pendiente de OCR; todavía no es evidencia aceptada"
        else:
            state = f"rechazado: {result.identity_reason}"
        self.pdf_review_status.set(f"PDF inspeccionado · {state}.")

    def _pdf_review_open_inspection(self, inspection: PdfInspection):
        self._pdf_review_current_url = inspection.url
        self._pdf_review_page_index = 0
        self._pdf_review_zoom = 1.0
        self._pdf_review_fit_mode = "width"
        self._pdf_review_update_detail(inspection)
        self._pdf_review_render_current_page()

    def _current_inspection(self) -> PdfInspection | None:
        index = self._pdf_review_product_index()
        if index is None or not self._pdf_review_current_url:
            return None
        return self._pdf_review_inspections.get(index, {}).get(self._pdf_review_current_url)

    def _pdf_review_go_page(self, action: str):
        inspection = self._current_inspection()
        if inspection is None:
            return
        last = max(0, inspection.page_count - 1)
        if action == "first": self._pdf_review_page_index = 0
        elif action == "prev": self._pdf_review_page_index = max(0, self._pdf_review_page_index - 1)
        elif action == "next": self._pdf_review_page_index = min(last, self._pdf_review_page_index + 1)
        elif action == "last": self._pdf_review_page_index = last
        self._pdf_review_render_current_page()

    def _pdf_review_change_zoom(self, delta: float):
        self._pdf_review_fit_mode = "zoom"
        self._pdf_review_zoom = max(0.5, min(2.0, self._pdf_review_zoom + float(delta)))
        self._pdf_review_render_current_page()

    def _pdf_review_set_fit(self, mode: str):
        self._pdf_review_fit_mode = "page" if mode == "page" else "width"
        self._pdf_review_render_current_page()

    def _pdf_review_rerender_if_fit(self):
        if self._pdf_review_fit_mode in {"width", "page"} and self._current_inspection() is not None:
            self.after(80, self._pdf_review_render_current_page)

    def _pdf_review_mousewheel(self, event):
        self.pdf_review_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def _pdf_review_ctrl_mousewheel(self, event):
        self._pdf_review_change_zoom(0.25 if event.delta > 0 else -0.25)
        return "break"

    def _pdf_review_render_current_page(self):
        inspection = self._current_inspection()
        if inspection is None:
            return
        index = max(0, min(self._pdf_review_page_index, inspection.page_count - 1))
        self._pdf_review_page_index = index
        render_zoom = self._pdf_review_zoom if self._pdf_review_fit_mode == "zoom" else 2.0
        cache_key = (inspection.url, index, int(render_zoom * 100), self._pdf_review_fit_mode)
        png = self._pdf_review_render_cache.get(cache_key)
        if png is None:
            try:
                png = render_pdf_page(inspection.local_path, index, render_zoom)
                self._pdf_review_render_cache[cache_key] = png
            except Exception as exc:
                self.pdf_review_status.set(f"No se pudo renderizar página {index + 1}: {exc}")
                return
        try:
            image = Image.open(BytesIO(png)).convert("RGB")
            canvas_w = max(200, self.pdf_review_canvas.winfo_width() - 20)
            canvas_h = max(200, self.pdf_review_canvas.winfo_height() - 20)
            if self._pdf_review_fit_mode == "width" and image.width > 0:
                target_w = canvas_w
                target_h = max(1, round(image.height * target_w / image.width))
                image = image.resize((target_w, target_h), Image.Resampling.LANCZOS)
            elif self._pdf_review_fit_mode == "page" and image.width > 0 and image.height > 0:
                ratio = min(canvas_w / image.width, canvas_h / image.height)
                image = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self._pdf_review_photo = photo
            self.pdf_review_canvas.delete("all")
            self.pdf_review_canvas.create_image(0, 0, image=photo, anchor="nw")
            self.pdf_review_canvas.configure(scrollregion=(0, 0, image.width, image.height))
            self.pdf_review_page_label.set(f"Página {index + 1} / {inspection.page_count}")
            if self._pdf_review_fit_mode == "zoom":
                self.pdf_review_zoom_label.set(f"{int(self._pdf_review_zoom * 100)}%")
            else:
                self.pdf_review_zoom_label.set("Ajustado")
        except Exception as exc:
            self.pdf_review_status.set(f"No se pudo mostrar la página: {exc}")

    def _pdf_review_update_detail(self, inspection: PdfInspection):
        if inspection.identity_provenance_bound:
            identity_label = "PROVENANCE_BOUND"
        elif inspection.identity_accepted:
            identity_label = "ACEPTADA"
        elif inspection.identity_pending_ocr:
            identity_label = "PENDIENTE OCR"
        else:
            identity_label = "RECHAZADA"
        ocr_label = "Sí, durante ejecución después de aprobar" if inspection.ocr_recommended else "No; texto nativo suficiente"
        provenance = ""
        if inspection.provenance:
            provenance = f"\nLanding padre: {inspection.provenance.parent_url}\nVínculo: {inspection.provenance.discovery_method} · {inspection.provenance.parent_authority}"
        pending_note = "\nIMPORTANTE: PENDIENTE OCR no es evidencia; OCR deberá confirmar identidad durante la ejecución." if inspection.identity_pending_ocr else ""
        self.pdf_review_detail.set(
            f"Score: {inspection.review_score}/100\n"
            f"Identidad: {identity_label} · {inspection.identity_reason} · confianza {inspection.identity_confidence:.2f}\n"
            f"Páginas: {inspection.page_count} · texto nativo: {inspection.native_text_chars} caracteres\n"
            f"OCR: {ocr_label}{provenance}\n"
            f"URL: {inspection.final_url}{pending_note}\n\n"
            "La vista previa solo usa texto nativo/render de PDF. No ejecuta OCR ni Mistral."
        )

    def _pdf_review_toggle_use(self):
        pair = self._pdf_review_selected_candidate()
        if pair is None:
            messagebox.showinfo("Revisión PDF", "Selecciona un PDF primero.")
            return
        index, candidate = pair
        inspection = self._pdf_review_inspections.get(index, {}).get(candidate.url)
        if inspection is None:
            messagebox.showinfo("Revisión PDF", "Primero abre la vista previa de este PDF.")
            self._pdf_review_inspect_selected()
            return
        if not inspection.identity_accepted and not inspection.identity_pending_ocr:
            messagebox.showwarning("Revisión PDF", "Este PDF fue rechazado por identidad y no puede usarse como evidencia.")
            return
        selected = self._pdf_review_selected.setdefault(index, set())
        if candidate.url in selected: selected.remove(candidate.url)
        else: selected.add(candidate.url)
        self._pdf_review_enforced.discard(index)
        self._pdf_review_refresh_tree()
        self.pdf_review_status.set(f"Selección pendiente de confirmar: {len(selected)} PDF(s).")

    def _pdf_review_confirm(self):
        index = self._pdf_review_product_index()
        if index is None:
            messagebox.showinfo("Revisión PDF", "Selecciona un producto primero.")
            return
        if self.pdf_review_mode.get() != "reviewed":
            messagebox.showinfo("Revisión PDF", "El modo Automático no usa una lista manual. Cambia a Revisar antes de usar para imponer tu selección.")
            return
        selected = self._pdf_review_selected.setdefault(index, set())
        self._pdf_review_enforced.add(index)
        self.pdf_review_status.set(f"Selección confirmada: {len(selected)} PDF(s). Solo estos PDFs podrán aportar evidencia para este producto.")

    def run(self):
        rows = list(getattr(self, "product_rows", []) or [])
        reviewed = [sorted(self._pdf_review_selected.get(index, set())) for index in range(len(rows))]
        reviewed_mode = getattr(self, "pdf_review_mode", None) is not None and self.pdf_review_mode.get() == "reviewed"
        flags = [reviewed_mode and index in self._pdf_review_enforced for index in range(len(rows))]
        set_desktop_review_plan(reviewed, flags)
        return super().run()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()