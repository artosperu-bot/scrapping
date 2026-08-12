from __future__ import annotations

import queue
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk

from .media_progress_desktop import App as MediaProgressApp
from .price_models import format_money
from .price_workflow import run_price_product


class App(MediaProgressApp):
    """Final desktop extension: tabs 1-7 plus independent price intelligence tab 8."""

    def __init__(self):
        self.price_events: queue.Queue = queue.Queue()
        self._price_running = False
        self._price_total = 0
        self._price_completed = 0
        self._price_current = 0
        super().__init__()
        self.after(150, self._drain_price_events)

    def _build(self):
        super()._build()
        self._build_price_tab()

    def _build_price_tab(self):
        self.price_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.price_tab, text="8. Precios y competencia")
        ttk.Label(self.price_tab, text="Inteligencia de precios por Part Number/modelo", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(self.price_tab, text="Descubre ofertas automáticamente, valida el producto y separa canal de vendedor real.").pack(anchor="w", pady=(1, 7))

        top = ttk.Frame(self.price_tab)
        top.pack(fill="x")
        left = ttk.LabelFrame(top, text="Productos", padding=8)
        left.pack(side="left", fill="y")
        self.price_product_list = tk.Listbox(left, exportselection=False, width=34, height=8)
        self.price_product_list.pack(fill="both", expand=True)

        right = ttk.LabelFrame(top, text="Acciones", padding=8)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.price_selected_btn = ttk.Button(right, text="BUSCAR PRECIOS", command=self._run_price_selected)
        self.price_selected_btn.pack(side="left")
        self.price_all_btn = ttk.Button(right, text="Procesar todos los productos", command=self._run_price_all)
        self.price_all_btn.pack(side="left", padx=8)
        self.price_status = tk.StringVar(value="Analiza un Excel para cargar productos.")
        ttk.Label(right, textvariable=self.price_status, font=("Segoe UI", 9, "bold"), wraplength=600).pack(anchor="w", pady=(38, 0))

        progress = ttk.LabelFrame(self.price_tab, text="Progreso", padding=8)
        progress.pack(fill="x", pady=(8, 6))
        row1 = ttk.Frame(progress); row1.pack(fill="x")
        ttk.Label(row1, text="Producto actual", width=15).pack(side="left")
        self.price_product_progress = ttk.Progressbar(row1, maximum=100, mode="determinate")
        self.price_product_progress.pack(side="left", fill="x", expand=True, padx=6)
        self.price_product_percent = tk.StringVar(value="0%")
        ttk.Label(row1, textvariable=self.price_product_percent, width=6).pack(side="left")
        row2 = ttk.Frame(progress); row2.pack(fill="x", pady=(4, 0))
        ttk.Label(row2, text="Progreso general", width=15).pack(side="left")
        self.price_overall_progress = ttk.Progressbar(row2, maximum=100, mode="determinate")
        self.price_overall_progress.pack(side="left", fill="x", expand=True, padx=6)
        self.price_overall_percent = tk.StringVar(value="0%")
        ttk.Label(row2, textvariable=self.price_overall_percent, width=6).pack(side="left")

        summary = ttk.Frame(self.price_tab)
        summary.pack(fill="x", pady=(0, 5))
        self.price_summary = tk.StringVar(value="Sin resultados todavía.")
        ttk.Label(summary, textvariable=self.price_summary, font=("Segoe UI", 9, "bold")).pack(anchor="w")

        box = ttk.LabelFrame(self.price_tab, text="Ofertas validadas", padding=5)
        box.pack(fill="both", expand=True)
        columns = ("product", "channel", "seller", "price", "list_price", "stock", "confidence", "url")
        self.price_tree = ttk.Treeview(box, columns=columns, show="headings", selectmode="browse")
        headings = {"product": "Producto", "channel": "Canal", "seller": "Vendedor", "price": "Precio", "list_price": "Precio lista", "stock": "Stock", "confidence": "Conf.", "url": "Enlace"}
        widths = {"product": 150, "channel": 100, "seller": 150, "price": 105, "list_price": 105, "stock": 65, "confidence": 65, "url": 260}
        for col in columns:
            self.price_tree.heading(col, text=headings[col])
            self.price_tree.column(col, width=widths[col], anchor="w")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.price_tree.yview)
        self.price_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.price_tree.pack(side="left", fill="both", expand=True)
        self.price_tree.bind("<Double-1>", self._open_price_offer)

    def analyze_excel(self):
        if hasattr(self, "price_product_list"):
            self.price_product_list.delete(0, "end")
        super().analyze_excel()
        if not hasattr(self, "price_product_list"):
            return
        for i, row in enumerate(self.product_rows):
            ident = self._identity_for_index(i)
            label = ident.mpn or ident.ean or ident.upc or ident.gtin or ident.model or ident.product_name if ident else row.get("model") or row.get("product_name") or f"Producto {i+1}"
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
        self.price_selected_btn.configure(state="disabled")
        self.price_all_btn.configure(state="disabled")
        for item in self.price_tree.get_children():
            self.price_tree.delete(item)
        self._set_price_progress(0, 0)

        def work():
            try:
                for pos, (index, identity) in enumerate(valid, 1):
                    label = identity.mpn or identity.model or identity.product_name or f"Producto {index+1}"
                    self.price_events.put({"type": "batch_product", "position": pos, "total": len(valid), "label": label})
                    def on_event(event, product_index=index, product_label=label):
                        self.price_events.put({**event, "product_index": product_index, "product_label": product_label})
                    run_price_product(identity, output_root, on_event=on_event, max_sources=12)
            except Exception:
                self.price_events.put({"type": "fatal", "error": traceback.format_exc()})
            finally:
                self.price_events.put({"type": "batch_done"})
        threading.Thread(target=work, daemon=True).start()

    def _drain_price_events(self):
        try:
            while True:
                event = self.price_events.get_nowait()
                kind = event.get("type")
                if kind == "batch_product":
                    self._price_current = int(event.get("position") or 1)
                    self.price_status.set(f"{self._price_current}/{self._price_total} — {event.get('label')} — buscando")
                    self._set_price_progress(10, int(((self._price_current - 1) / self._price_total) * 100))
                elif kind == "status":
                    stage = str(event.get("stage") or "")
                    pct = {"searching": 20, "validating": 55, "saving": 90}.get(stage, 30)
                    overall = int((((self._price_current - 1) + pct / 100) / max(1, self._price_total)) * 100)
                    self._set_price_progress(pct, overall)
                    self.price_status.set(str(event.get("message") or stage))
                elif kind == "offer" and event.get("offer"):
                    self._insert_price_offer(event["offer"], event.get("product_label"))
                elif kind == "page":
                    self.price_status.set(f"{event.get('channel')}: {event.get('status')}")
                elif kind == "done":
                    self._price_completed += 1
                    overall = int((self._price_completed / max(1, self._price_total)) * 100)
                    self._set_price_progress(100, overall)
                    best_by_currency = event.get("best_by_currency") or {}
                    best_text = " · ".join(format_money(value, currency) for currency, value in sorted(best_by_currency.items())) or "sin oferta válida"
                    self.price_summary.set(f"{self._price_completed}/{self._price_total} productos · {event.get('offers', 0)} ofertas en este producto · mejores precios: {best_text}")
                elif kind == "fatal":
                    self.price_status.set("Error general durante la búsqueda de precios.")
                    self.emit(event.get("error") or "Error de precios")
                elif kind == "batch_done":
                    self._price_running = False
                    self.price_selected_btn.configure(state="normal")
                    self.price_all_btn.configure(state="normal")
                    if self._price_completed >= self._price_total:
                        self._set_price_progress(100, 100)
                        self.price_status.set("Proceso de precios completado.")
        except queue.Empty:
            pass
        self.after(150, self._drain_price_events)

    def _set_price_progress(self, product_pct: int, overall_pct: int):
        self.price_product_progress["value"] = max(0, min(100, product_pct))
        self.price_overall_progress["value"] = max(0, min(100, overall_pct))
        self.price_product_percent.set(f"{int(product_pct)}%")
        self.price_overall_percent.set(f"{int(overall_pct)}%")

    def _insert_price_offer(self, row: dict, label: str | None):
        price = row.get("selling_price")
        list_price = row.get("list_price")
        currency = str(row.get("currency") or "PEN")
        self.price_tree.insert("", "end", values=(label or row.get("part_number") or row.get("model") or "", row.get("channel") or "", row.get("seller_display_name") or "No expuesto", format_money(price, currency), format_money(list_price, currency), row.get("stock") if row.get("stock") is not None else "", f"{float(row.get('confidence') or 0):.2f}", row.get("url") or ""))

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
