from __future__ import annotations

from datetime import datetime
import queue
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk

from .media_progress_desktop import App as MediaProgressApp
from .price_models import format_money
from .price_workflow import run_price_product
from .progress_animation import ProgressAnimation


class App(MediaProgressApp):
    """Final desktop extension: tabs 1-7 plus self-contained Price Intelligence tab 8."""

    def __init__(self):
        self.price_events: queue.Queue = queue.Queue()
        self._price_running = False
        self._price_total = 0
        self._price_completed = 0
        self._price_current = 0
        self._price_had_error = False
        self._price_offer_count = 0
        self._price_last_coverage: dict = {}
        super().__init__()
        self.after(150, self._drain_price_events)

    def _build(self):
        super()._build()
        self._build_price_tab()

    def _build_price_tab(self):
        self.price_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.price_tab, text="8. Precios y competencia")
        ttk.Label(self.price_tab, text="Inteligencia de precios por Part Number/modelo", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(self.price_tab, text="Descubre ofertas, valida identidad y deja ofertas, cobertura y auditoría visibles en este mismo módulo.").pack(anchor="w", pady=(1, 8))

        top = ttk.Frame(self.price_tab)
        top.pack(fill="x")
        left = ttk.LabelFrame(top, text="Productos detectados", padding=10)
        left.pack(side="left", fill="y")
        self.price_product_list = tk.Listbox(left, exportselection=False, width=34, height=8)
        self.price_product_list.pack(fill="both", expand=True)

        right = ttk.LabelFrame(top, text="Acciones y estado actual", padding=10)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        actions_row = ttk.Frame(right)
        actions_row.pack(fill="x")
        self.price_selected_btn = ttk.Button(actions_row, text="BUSCAR PRECIOS", command=self._run_price_selected)
        self.price_selected_btn.pack(side="left")
        self.price_all_btn = ttk.Button(actions_row, text="Procesar todos los productos", command=self._run_price_all)
        self.price_all_btn.pack(side="left", padx=(8, 0))
        self.price_status = tk.StringVar(value="Analiza un Excel para cargar productos.")
        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=(10, 8))
        ttk.Label(right, text="Estado", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(right, textvariable=self.price_status, wraplength=760, justify="left").pack(anchor="w", fill="x", pady=(3, 0))

        progress = ttk.LabelFrame(self.price_tab, text="Progreso del proceso", padding=10, height=190)
        progress.pack(fill="x", pady=(10, 6))
        progress.pack_propagate(False)
        progress_info = ttk.Frame(progress)
        progress_info.pack(side="left", fill="both", expand=True, padx=(0, 12))
        progress_visual = ttk.Frame(progress)
        progress_visual.pack(side="right", fill="y")

        ttk.Label(progress_info, text="Seguimiento", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(progress_info, textvariable=self.price_status, wraplength=720, justify="left").pack(anchor="w", fill="x", pady=(3, 10))

        row1 = ttk.Frame(progress_info)
        row1.pack(fill="x", pady=(0, 5))
        ttk.Label(row1, text="Producto actual", width=16).pack(side="left")
        self.price_product_progress = ttk.Progressbar(row1, maximum=100, mode="determinate")
        self.price_product_progress.pack(side="left", fill="x", expand=True, padx=(6, 8))
        self.price_product_percent = tk.StringVar(value="0%")
        ttk.Label(row1, textvariable=self.price_product_percent, width=9).pack(side="left")

        row2 = ttk.Frame(progress_info)
        row2.pack(fill="x")
        ttk.Label(row2, text="Progreso general", width=16).pack(side="left")
        self.price_overall_progress = ttk.Progressbar(row2, maximum=100, mode="determinate")
        self.price_overall_progress.pack(side="left", fill="x", expand=True, padx=(6, 8))
        self.price_overall_percent = tk.StringVar(value="0%")
        ttk.Label(row2, textvariable=self.price_overall_percent, width=9).pack(side="left")

        self.price_progress_animation = ProgressAnimation(progress_visual, width=220, height=140)
        self.price_progress_animation.pack(anchor="center")

        summary = ttk.LabelFrame(self.price_tab, text="Resumen", padding=(8, 5))
        summary.pack(fill="x", pady=(0, 6))
        self.price_summary = tk.StringVar(value="Sin resultados todavía.")
        ttk.Label(summary, textvariable=self.price_summary, font=("Segoe UI", 9, "bold"), wraplength=1100, justify="left").pack(anchor="w")

        self.price_results_notebook = ttk.Notebook(self.price_tab)
        self.price_results_notebook.pack(fill="both", expand=True)

        offers_tab = ttk.Frame(self.price_results_notebook, padding=5)
        coverage_tab = ttk.Frame(self.price_results_notebook, padding=5)
        audit_tab = ttk.Frame(self.price_results_notebook, padding=5)
        self.price_results_notebook.add(offers_tab, text="Ofertas")
        self.price_results_notebook.add(coverage_tab, text="Cobertura")
        self.price_results_notebook.add(audit_tab, text="Auditoría")

        columns = ("product", "channel", "seller", "price", "list_price", "stock", "confidence", "url")
        self.price_tree = ttk.Treeview(offers_tab, columns=columns, show="headings", selectmode="browse")
        headings = {"product": "Producto", "channel": "Canal", "seller": "Vendedor", "price": "Precio", "list_price": "Precio lista", "stock": "Stock", "confidence": "Conf.", "url": "Enlace"}
        widths = {"product": 150, "channel": 110, "seller": 160, "price": 105, "list_price": 105, "stock": 70, "confidence": 70, "url": 280}
        for col in columns:
            self.price_tree.heading(col, text=headings[col])
            self.price_tree.column(col, width=widths[col], anchor="w")
        offer_scroll = ttk.Scrollbar(offers_tab, orient="vertical", command=self.price_tree.yview)
        self.price_tree.configure(yscrollcommand=offer_scroll.set)
        offer_scroll.pack(side="right", fill="y")
        self.price_tree.pack(side="left", fill="both", expand=True)
        self.price_tree.bind("<Double-1>", self._open_price_offer)

        coverage_columns = ("channel", "status", "offers", "detail")
        self.price_coverage_tree = ttk.Treeview(coverage_tab, columns=coverage_columns, show="headings", selectmode="browse")
        for col, title, width in (
            ("channel", "Canal", 180),
            ("status", "Estado", 110),
            ("offers", "Ofertas", 80),
            ("detail", "Detalle", 650),
        ):
            self.price_coverage_tree.heading(col, text=title)
            self.price_coverage_tree.column(col, width=width, anchor="w")
        coverage_scroll = ttk.Scrollbar(coverage_tab, orient="vertical", command=self.price_coverage_tree.yview)
        self.price_coverage_tree.configure(yscrollcommand=coverage_scroll.set)
        coverage_scroll.pack(side="right", fill="y")
        self.price_coverage_tree.pack(side="left", fill="both", expand=True)

        audit_columns = ("time", "stage", "source", "status", "detail")
        self.price_audit_tree = ttk.Treeview(audit_tab, columns=audit_columns, show="headings", selectmode="browse")
        for col, title, width in (
            ("time", "Hora", 90),
            ("stage", "Etapa", 130),
            ("source", "Fuente", 160),
            ("status", "Estado", 110),
            ("detail", "Detalle", 680),
        ):
            self.price_audit_tree.heading(col, text=title)
            self.price_audit_tree.column(col, width=width, anchor="w")
        audit_scroll = ttk.Scrollbar(audit_tab, orient="vertical", command=self.price_audit_tree.yview)
        self.price_audit_tree.configure(yscrollcommand=audit_scroll.set)
        audit_scroll.pack(side="right", fill="y")
        self.price_audit_tree.pack(side="left", fill="both", expand=True)

    def analyze_excel(self):
        if hasattr(self, "price_product_list"):
            self.price_product_list.delete(0, "end")
        super().analyze_excel()
        if not hasattr(self, "price_product_list"):
            return
        for i, row in enumerate(self.product_rows):
            ident = self._identity_for_index(i)
            label = ident.mpn or ident.ean or ident.upc or ident.gtin or ident.sku or ident.model or ident.product_name if ident else row.get("model") or row.get("product_name") or f"Producto {i+1}"
            self.price_product_list.insert("end", str(label))
        if self.product_rows:
            self.price_product_list.selection_set(0)
            self.price_status.set(f"{len(self.product_rows)} productos listos para comparar precios.")

    def _selected_price_index(self):
        sel = self.price_product_list.curselection()
        return int(sel[0]) if sel else None

    def _run_price_selected(self):
        index = self._selected_price_index()
        if index is None:
            messagebox.showwarning("Precios", "Selecciona primero un producto.")
            return
        self._start_price_indices([index])

    def _run_price_all(self):
        if not self.product_rows:
            messagebox.showwarning("Precios", "Analiza primero un Excel con productos.")
            return
        self._start_price_indices(list(range(len(self.product_rows))))

    def _clear_price_results(self):
        self._price_offer_count = 0
        self._price_last_coverage = {}
        for tree in (self.price_tree, self.price_coverage_tree, self.price_audit_tree):
            for item in tree.get_children():
                tree.delete(item)
        self.price_summary.set("Buscando precios…")

    def _start_price_indices(self, indices):
        if self._price_running:
            messagebox.showinfo("Precios", "Ya hay una búsqueda de precios en ejecución.")
            return
        valid = [(i, self._identity_for_index(i)) for i in indices if self._identity_for_index(i) is not None]
        if not valid:
            messagebox.showerror("Precios", "No hay identidades válidas para procesar.")
            return
        output_root = self.out.get()
        self._price_running = True
        self._price_total = len(valid)
        self._price_completed = 0
        self._price_had_error = False
        self.price_selected_btn.configure(state="disabled")
        self.price_all_btn.configure(state="disabled")
        self._clear_price_results()
        self._set_price_progress(0, 0)
        self.price_progress_animation.set_running("Consultando precios…")

        def work():
            try:
                for pos, (index, identity) in enumerate(valid, 1):
                    label = identity.mpn or identity.model or identity.product_name or f"Producto {index+1}"
                    self.price_events.put({"type": "batch_product", "position": pos, "total": len(valid), "label": label})

                    def on_event(event, product_index=index, product_label=label):
                        self.price_events.put({**event, "product_index": product_index, "product_label": product_label})

                    # The workflow is intentionally designed to interleave multiple source families.
                    # Use the full budget so one sparse family cannot make the whole search look empty.
                    run_price_product(identity, output_root, on_event=on_event, max_sources=48)
            except Exception:
                self.price_events.put({"type": "fatal", "error": traceback.format_exc()})
            finally:
                self.price_events.put({"type": "batch_done"})

        threading.Thread(target=work, daemon=True).start()

    def _start_price_product_indicator(self):
        self.price_product_progress.stop()
        self.price_product_progress.configure(mode="indeterminate")
        self.price_product_progress.start(12)
        self.price_product_percent.set("En curso")

    @staticmethod
    def _audit_detail(event: dict) -> str:
        if event.get("message"):
            return str(event.get("message"))
        if event.get("error"):
            return str(event.get("error"))
        pieces = []
        for key in ("offers", "urls", "position", "total", "method"):
            if event.get(key) is not None:
                pieces.append(f"{key}={event.get(key)}")
        return " · ".join(pieces) or str(event.get("status") or event.get("type") or "")

    def _append_price_audit(self, event: dict):
        if not hasattr(self, "price_audit_tree"):
            return
        kind = str(event.get("type") or "")
        source = str(event.get("channel") or event.get("source") or "")
        status = str(event.get("status") or ("ERROR" if kind == "fatal" else "PROGRESS"))
        stage = str(event.get("stage") or kind)
        self.price_audit_tree.insert(
            "",
            "end",
            values=(datetime.now().strftime("%H:%M:%S"), stage, source, status, self._audit_detail(event)),
        )

    def _render_price_coverage(self, report: dict):
        self._price_last_coverage = dict(report or {})
        for item in self.price_coverage_tree.get_children():
            self.price_coverage_tree.delete(item)
        channels = list((report or {}).get("channels") or [])
        found = 0
        no_hay = 0
        for row in channels:
            status = str(row.get("status") or "NO_HAY")
            offers = list(row.get("offers") or [])
            if status == "FOUND":
                found += 1
            if status == "NO_HAY":
                no_hay += 1
            aliases = ", ".join(str(v) for v in (row.get("aliases") or []) if v)
            detail = f"Aliases: {aliases}" if aliases else ("Sin oferta válida encontrada" if status == "NO_HAY" else "Oferta(s) validada(s)")
            self.price_coverage_tree.insert(
                "",
                "end",
                values=(row.get("channel") or "", row.get("status") or "NO_HAY", len(offers), detail),
            )
        individual = int((report or {}).get("individual_store_count") or 0)
        self.price_summary.set(
            f"Cobertura: {len(channels)} canales revisados · {found} con oferta · {no_hay} sin oferta · {individual} tiendas adicionales"
        )

    def _drain_price_events(self):
        try:
            while True:
                event = self.price_events.get_nowait()
                kind = event.get("type")
                try:
                    if kind not in {"offer"}:
                        self._append_price_audit(event)
                    if kind == "batch_product":
                        self._price_current = int(event.get("position") or 1)
                        label = str(event.get("label") or "")
                        self.price_status.set(f"{self._price_current}/{self._price_total} — {label} — buscando")
                        self._start_price_product_indicator()
                        overall = int((self._price_completed / max(1, self._price_total)) * 100)
                        self.price_overall_progress["value"] = overall
                        self.price_overall_percent.set(f"{overall}%")
                        self.price_progress_animation.set_running(f"Consultando precios · producto {self._price_current} de {self._price_total}")
                    elif kind == "status":
                        text = str(event.get("message") or event.get("stage") or "Consultando precios…")
                        self.price_status.set(text)
                        self.price_progress_animation.set_running(text)
                    elif kind == "offer" and event.get("offer"):
                        self._price_offer_count += 1
                        self._insert_price_offer(event["offer"], event.get("product_label"))
                    elif kind == "coverage":
                        self._render_price_coverage(event.get("report") or {})
                    elif kind == "page":
                        text = f"{event.get('channel')}: {event.get('status')}"
                        self.price_status.set(text)
                        self.price_progress_animation.set_running(text)
                    elif kind == "done":
                        self._price_completed += 1
                        overall = int((self._price_completed / max(1, self._price_total)) * 100)
                        self._set_price_progress(100, overall)
                        offer_count = int(event.get("offers") or 0)
                        if offer_count == 0:
                            self.price_summary.set("Búsqueda completada · 0 ofertas válidas · revisa Cobertura para ver cada canal consultado.")
                        else:
                            best_by_currency = event.get("best_by_currency") or {}
                            best_text = " · ".join(format_money(value, currency) for currency, value in sorted(best_by_currency.items())) or "sin mínimo calculable"
                            self.price_summary.set(
                                f"Búsqueda completada · {offer_count} ofertas válidas · {event.get('channels', 0)} canales con oferta · mejores precios: {best_text}"
                            )
                    elif kind == "fatal":
                        self._price_had_error = True
                        error = str(event.get("error") or "Error de precios")
                        self.price_product_progress.stop()
                        self.price_product_progress.configure(mode="determinate")
                        self.price_status.set(error)
                        self.price_progress_animation.set_error(error)
                        self.emit(error)
                    elif kind == "batch_done":
                        self._price_running = False
                        self.price_product_progress.stop()
                        self.price_selected_btn.configure(state="normal")
                        self.price_all_btn.configure(state="normal")
                        if self._price_had_error:
                            self.price_product_progress.configure(mode="determinate")
                            self.price_product_percent.set("Error")
                        elif self._price_completed >= self._price_total:
                            self._set_price_progress(100, 100)
                            self.price_status.set("Proceso completado")
                            self.price_progress_animation.set_completed("Proceso completado")
                        else:
                            self._price_had_error = True
                            error = f"Finalización incompleta: el proceso terminó, pero la interfaz recibió {self._price_completed}/{self._price_total} confirmaciones finales."
                            self.price_product_progress.configure(mode="determinate")
                            self.price_product_percent.set("Error")
                            self.price_status.set(error)
                            self.price_progress_animation.set_error(error)
                            self.emit(error)
                except Exception as exc:
                    self._price_had_error = True
                    error = f"Error actualizando interfaz de precios ({kind or 'evento'}): {type(exc).__name__}: {exc}"
                    try:
                        self.price_product_progress.stop()
                        self.price_product_progress.configure(mode="determinate")
                        self.price_product_percent.set("Error")
                        self.price_status.set(error)
                        self.price_progress_animation.set_error(error)
                    except Exception:
                        pass
                    self.emit(f"{error}\n{traceback.format_exc()}")
        except queue.Empty:
            pass
        finally:
            self.after(150, self._drain_price_events)

    def _set_price_progress(self, product_pct: int, overall_pct: int):
        self.price_product_progress.stop()
        self.price_product_progress.configure(mode="determinate")
        product_pct = max(0, min(100, product_pct))
        overall_pct = max(0, min(100, overall_pct))
        self.price_product_progress["value"] = product_pct
        self.price_overall_progress["value"] = overall_pct
        self.price_product_percent.set(f"{int(product_pct)}%")
        self.price_overall_percent.set(f"{int(overall_pct)}%")

    def _insert_price_offer(self, row: dict, label: str | None):
        price = row.get("selling_price")
        list_price = row.get("list_price")
        currency = str(row.get("currency") or "PEN")
        self.price_tree.insert(
            "",
            "end",
            values=(
                label or row.get("part_number") or row.get("model") or "",
                row.get("channel") or "",
                row.get("seller_display_name") or "No expuesto",
                format_money(price, currency),
                format_money(list_price, currency),
                row.get("stock") if row.get("stock") is not None else "",
                f"{float(row.get('confidence') or 0):.2f}",
                row.get("url") or "",
            ),
        )

    def _open_price_offer(self, _event=None):
        item = self.price_tree.focus()
        if not item:
            return
        values = self.price_tree.item(item, "values")
        if values and len(values) >= 8 and values[7]:
            webbrowser.open(str(values[7]))


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
