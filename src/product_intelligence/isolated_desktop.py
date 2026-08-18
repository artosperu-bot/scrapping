from __future__ import annotations

import json
import threading
import traceback
import tkinter as tk
from tkinter import messagebox, ttk

from .audit_events import AuditEvent, AuditSink, filter_events
from .batch import run_batch
from .execution_context import ExecutionSnapshot, ProductSnapshot
from .media_workflow import run_media_product
from .modern_desktop import App as ModernApp
from .price_workflow import run_price_product


class App(ModernApp):
    """Ordered desktop orchestration with isolated EXCEL/MEDIA/PRICE runs."""

    def __init__(self):
        self.audit_sink = AuditSink()
        self._audit_rendered = 0
        self._active_snapshots: dict[str, ExecutionSnapshot] = {}
        super().__init__()
        self._install_ordered_navigation()
        self._install_structured_audit()
        self.after(200, self._refresh_audit_view)

    @staticmethod
    def _copy_identity(identity):
        if identity is None:
            return None
        copier = getattr(identity, "model_copy", None)
        return copier(deep=True) if copier else identity

    def _product_snapshot(self, index: int, manual_urls=()) -> ProductSnapshot | None:
        identity = self._identity_for_index(index)
        if identity is None:
            return None
        copied = self._copy_identity(identity)
        label = str(copied.mpn or copied.ean or copied.upc or copied.gtin or copied.model or copied.product_name or f"Producto {index + 1}")
        return ProductSnapshot(index=index, label=label, identity=copied, manual_urls=tuple(manual_urls))

    def _price_product_snapshot(self, index: int) -> ProductSnapshot | None:
        identity = self._price_identity_for_list_index(index)
        if identity is None:
            return None
        copied = self._copy_identity(identity)
        label = str(copied.mpn or copied.ean or copied.upc or copied.gtin or copied.model or copied.product_name or f"Producto {index + 1}")
        return ProductSnapshot(index=index, label=label, identity=copied)

    def _audit(self, snapshot: ExecutionSnapshot, *, status: str, stage: str = "", product_id: str = "", source: str = "", url: str = "", detail: str = "", result: str = ""):
        self.audit_sink.emit(AuditEvent.create(snapshot.run_id, snapshot.process_type, status=status, stage=stage, product_id=product_id, source=source, url=url, detail=detail, result=result))

    def _install_ordered_navigation(self):
        # Keep the existing functional pages, but present them under one Excel process.
        for key in ("sources", "attributes", "run"):
            button = self._nav_buttons.get(key)
            if button is not None:
                button.pack_forget()
        products_button = self._nav_buttons.get("products")
        if products_button is not None:
            products_button.configure(text="▦   Scraping Excel", command=lambda: self._show_workspace("products"))

        for key in ("products", "sources", "attributes", "run"):
            tab_ref = self._workspace_tabs.get(key)
            if tab_ref is None:
                continue
            try:
                tab = self.nametowidget(str(tab_ref)) if isinstance(tab_ref, str) else tab_ref
                bar = ttk.Frame(tab, style="Card.TFrame", padding=(4, 4))
                bar.pack(fill="x", pady=(0, 8), before=tab.winfo_children()[0] if tab.winfo_children() else None)
                for label, target in (("Productos", "products"), ("Fuentes", "sources"), ("Atributos", "attributes"), ("Ejecutar", "run")):
                    ttk.Button(bar, text=label, command=lambda t=target: self._show_workspace(t)).pack(side="left", padx=(0, 6))
            except (tk.TclError, AttributeError, IndexError):
                continue

    def _install_structured_audit(self):
        tab_ref = self._workspace_tabs.get("audit")
        if tab_ref is None:
            return
        tab = self.nametowidget(str(tab_ref)) if isinstance(tab_ref, str) else tab_ref

        # Preserve the legacy raw Text widget for diagnostics but hide the old layout.
        for child in tab.winfo_children():
            child.pack_forget()

        controls = ttk.Frame(tab, style="Card.TFrame", padding=6)
        controls.pack(fill="x")
        ttk.Label(controls, text="Auditoría de ejecuciones", font=("Segoe UI", 11, "bold")).pack(side="left")
        self.audit_filter = tk.StringVar(value="Todos")
        ttk.Combobox(controls, textvariable=self.audit_filter, state="readonly", width=20, values=("Todos", "Scraping Excel", "Multimedia", "Precios", "Errores", "Rechazados")).pack(side="left", padx=10)
        self.audit_query = tk.StringVar()
        query = ttk.Entry(controls, textvariable=self.audit_query, width=30)
        query.pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Actualizar", command=self._render_audit).pack(side="left")
        ttk.Button(controls, text="Log técnico", command=self._show_raw_log).pack(side="right")
        self.audit_filter.trace_add("write", lambda *_: self._render_audit())
        self.audit_query.trace_add("write", lambda *_: self._render_audit())

        box = ttk.Frame(tab, style="Card.TFrame", padding=6)
        box.pack(fill="both", expand=True, pady=(8, 0))
        columns = ("time", "run", "process", "product", "stage", "source", "status", "detail")
        self.audit_tree = ttk.Treeview(box, columns=columns, show="headings", style="Modern.Treeview")
        headings = {"time": "Hora", "run": "Ejecución", "process": "Proceso", "product": "Producto", "stage": "Etapa", "source": "Fuente", "status": "Estado", "detail": "Detalle"}
        widths = {"time": 90, "run": 210, "process": 90, "product": 150, "stage": 120, "source": 120, "status": 90, "detail": 420}
        for col in columns:
            self.audit_tree.heading(col, text=headings[col])
            self.audit_tree.column(col, width=widths[col], anchor="w")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.audit_tree.yview)
        self.audit_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.audit_tree.pack(side="left", fill="both", expand=True)
        self.audit_tree.bind("<<TreeviewSelect>>", self._show_audit_detail)

        self.audit_detail = tk.StringVar(value="Selecciona un evento para ver URL y detalle técnico.")
        ttk.Label(tab, textvariable=self.audit_detail, wraplength=1100, justify="left").pack(fill="x", padx=6, pady=(6, 0))

    def _filtered_audit_events(self):
        value = self.audit_filter.get() if hasattr(self, "audit_filter") else "Todos"
        process = {"Scraping Excel": "EXCEL", "Multimedia": "MEDIA", "Precios": "PRICE"}.get(value)
        status = {"Errores": "ERROR", "Rechazados": "REJECTED"}.get(value)
        query = self.audit_query.get() if hasattr(self, "audit_query") else ""
        return filter_events(self.audit_sink.events(), process_type=process, status=status, query=query)

    def _render_audit(self):
        if not hasattr(self, "audit_tree"):
            return
        for item in self.audit_tree.get_children():
            self.audit_tree.delete(item)
        for pos, event in enumerate(self._filtered_audit_events()):
            time_text = event.timestamp[11:19] if len(event.timestamp) >= 19 else event.timestamp
            self.audit_tree.insert("", "end", iid=str(pos), values=(time_text, event.run_id, event.process_type, event.product_id, event.stage, event.source, event.status, event.detail), tags=(event.url, event.result))
        self._audit_rendered = len(self.audit_sink.events())

    def _refresh_audit_view(self):
        if len(self.audit_sink.events()) != self._audit_rendered:
            self._render_audit()
        self.after(200, self._refresh_audit_view)

    def _show_audit_detail(self, _event=None):
        selected = self.audit_tree.selection() if hasattr(self, "audit_tree") else ()
        if not selected:
            return
        idx = int(selected[0])
        events = self._filtered_audit_events()
        if 0 <= idx < len(events):
            event = events[idx]
            parts = [event.detail]
            if event.url:
                parts.append(f"URL: {event.url}")
            if event.result:
                parts.append(f"Resultado: {event.result}")
            self.audit_detail.set(" | ".join(part for part in parts if part))

    def _show_raw_log(self):
        win = tk.Toplevel(self)
        win.title("Log técnico")
        win.geometry("1000x650")
        text = tk.Text(win, wrap="word", font=("Consolas", 9))
        text.pack(fill="both", expand=True)
        try:
            text.insert("1.0", self.log.get("1.0", "end"))
        except tk.TclError:
            text.insert("1.0", "Log técnico no disponible.")
        text.configure(state="disabled")

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
        snapshot = ExecutionSnapshot.create("EXCEL", self.out.get(), products, workbook=self.excel.get(), overwrite=self.overwrite.get())
        self._active_snapshots[snapshot.run_id] = snapshot
        self.runbtn.configure(state="disabled")
        self._show_workspace("audit")
        self._audit(snapshot, status="STARTED", stage="inicio", detail=f"Scraping Excel iniciado con {len(products)} producto(s).")

        def work(job=snapshot):
            try:
                identities = [p.identity for p in job.products]
                urls = [list(p.manual_urls) for p in job.products]
                self.emit(f"=== {job.run_id} INICIO SCRAPING ===")
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

    def _start_media_indices(self, indices: list[int]):
        if self._media_running:
            messagebox.showinfo("Multimedia", "Ya hay una búsqueda multimedia en ejecución.")
            return
        products = []
        for index in indices:
            snap = self._product_snapshot(index, self.media_manual_urls.get(index, []))
            if snap:
                products.append(snap)
        if not products:
            messagebox.showerror("Multimedia", "No hay productos con identidad válida para procesar.")
            return
        snapshot = ExecutionSnapshot.create("MEDIA", self.out.get(), products, options={"auto_search": bool(self.media_auto_search.get())})
        self._active_snapshots[snapshot.run_id] = snapshot
        self._media_running = True
        self.media_selected_btn.configure(state="disabled")
        self.media_all_btn.configure(state="disabled")
        self._clear_media_gallery()
        self._audit(snapshot, status="STARTED", stage="inicio", detail=f"Multimedia iniciada con {len(products)} producto(s).")

        def work(job=snapshot):
            try:
                for pos, product in enumerate(job.products, 1):
                    self.media_events.put({"type": "batch_status", "message": f"{pos}/{len(job.products)} — {product.label}", "run_id": job.run_id})
                    def on_event(event, p=product):
                        event = {**event, "product_index": p.index, "product_label": p.label, "run_id": job.run_id}
                        self.media_events.put(event)
                        kind = str(event.get("type") or "")
                        status = "ERROR" if kind in {"error", "fatal"} else "REJECTED" if kind == "media_rejected" else "FOUND" if kind == "media" else "PROGRESS"
                        self._audit(job, status=status, stage=kind, product_id=p.label, source=str(event.get("source") or ""), url=str(event.get("url") or ""), detail=str(event.get("status") or event.get("error") or kind))
                    run_media_product(product.identity, job.output_root, manual_urls=list(product.manual_urls), auto_search=bool(job.option("auto_search", True)), max_pages=10, on_event=on_event)
                self._audit(job, status="DONE", stage="final", detail="Multimedia completada.")
            except Exception as exc:
                self.media_events.put({"type": "fatal", "error": traceback.format_exc(), "run_id": job.run_id})
                self._audit(job, status="ERROR", stage="fatal", detail=str(exc))
            finally:
                self.media_events.put({"type": "batch_done", "run_id": job.run_id})
                self._active_snapshots.pop(job.run_id, None)
        threading.Thread(target=work, daemon=True).start()

    def _start_price_indices(self, indices):
        if self._price_running:
            messagebox.showinfo("Precios", "Ya hay una búsqueda de precios en ejecución.")
            return
        products = [snap for index in indices if (snap := self._price_product_snapshot(index)) is not None]
        if not products:
            messagebox.showerror("Precios", "No hay identidades válidas para procesar.")
            return
        snapshot = ExecutionSnapshot.create("PRICE", self.out.get(), products)
        self._active_snapshots[snapshot.run_id] = snapshot
        self._price_running = True
        self._price_total = len(products)
        self._price_completed = 0
        self.price_selected_btn.configure(state="disabled")
        self.price_all_btn.configure(state="disabled")
        for item in self.price_tree.get_children():
            self.price_tree.delete(item)
        self._set_price_progress(0, 0)
        self._audit(snapshot, status="STARTED", stage="inicio", detail=f"Precios iniciados con {len(products)} producto(s).")

        def work(job=snapshot):
            try:
                for pos, product in enumerate(job.products, 1):
                    self.price_events.put({"type": "batch_product", "position": pos, "total": len(job.products), "label": product.label, "run_id": job.run_id})
                    def on_event(event, p=product):
                        event = {**event, "product_index": p.index, "product_label": p.label, "run_id": job.run_id}
                        self.price_events.put(event)
                        kind = str(event.get("type") or "")
                        status = "ERROR" if kind in {"error", "fatal"} else "FOUND" if kind == "offer" else "REJECTED" if str(event.get("status") or "").startswith("rejected") else "PROGRESS"
                        self._audit(job, status=status, stage=kind, product_id=p.label, source=str(event.get("channel") or ""), url=str(event.get("url") or ""), detail=str(event.get("status") or event.get("message") or kind))
                    run_price_product(product.identity, job.output_root, on_event=on_event, max_sources=12)
                self._audit(job, status="DONE", stage="final", detail="Precios completados.")
            except Exception as exc:
                self.price_events.put({"type": "fatal", "error": traceback.format_exc(), "run_id": job.run_id})
                self._audit(job, status="ERROR", stage="fatal", detail=str(exc))
            finally:
                self.price_events.put({"type": "batch_done", "run_id": job.run_id})
                self._active_snapshots.pop(job.run_id, None)
        threading.Thread(target=work, daemon=True).start()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
