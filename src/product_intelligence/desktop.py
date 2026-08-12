from __future__ import annotations

import json
import os
import queue
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def _configure_frozen_browser():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    bundled = base / "vendor" / "ms-playwright"
    if bundled.exists():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(bundled))


_configure_frozen_browser()

from .batch import run_batch
from .discovery import search_web
from .excel_mapper_v8 import fill_excel_v8
from .input_identity import parse_product_query
from .models import ProductIdentity, ProductRecord
from .preflight import analyze_workbook
from .repair import repair_existing_record


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Product Intelligence — Excel + Scraping web sin IA")
        self.geometry("1360x900")
        self.minsize(1120, 720)
        self.q = queue.Queue()
        self.preflight = None
        self.product_rows: list[dict] = []
        self.manual_urls: dict[int, list[str]] = {}
        self.source_preview: dict[int, list[dict]] = {}
        self._build()
        self.after(150, self._drain)

    def _build(self):
        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Product Intelligence", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            main,
            text="Excel → productos → URLs/fuentes → atributos → ejecución. El sistema completa solo lo verificable y deja trazabilidad.",
        ).pack(anchor="w", pady=(2, 8))

        top = ttk.LabelFrame(main, text="1. Plantilla Excel", padding=8)
        top.pack(fill="x")
        self.excel = tk.StringVar()
        ttk.Entry(top, textvariable=self.excel).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Elegir...", command=self.pick_excel).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="ANALIZAR EXCEL", command=self.analyze_excel).pack(side="left", padx=(8, 0))

        self.analysis_status = tk.StringVar(value="Selecciona un Excel y pulsa ANALIZAR EXCEL.")
        ttk.Label(main, textvariable=self.analysis_status, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(6, 5))

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="both", expand=True)

        self._build_products_tab()
        self._build_sources_tab()
        self._build_attrs_tab()
        self._build_run_tab()
        self._build_logs_tab()

    def _build_products_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="2. Productos")
        ttk.Label(tab, text="Productos detectados en el Excel", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(tab, text="El identificador puede ser MPN, EAN, UPC/GTIN, modelo o nombre. No necesitas mezclar aquí las URLs.").pack(anchor="w", pady=(1, 7))

        cols = ("row", "identifier", "brand", "model", "urls", "status")
        self.products_tree = ttk.Treeview(tab, columns=cols, show="headings", height=16)
        headings = {
            "row": "Fila",
            "identifier": "Identificador principal",
            "brand": "Marca",
            "model": "Modelo / nombre",
            "urls": "URLs manuales",
            "status": "Estado",
        }
        widths = {"row": 55, "identifier": 270, "brand": 150, "model": 330, "urls": 110, "status": 150}
        for col in cols:
            self.products_tree.heading(col, text=headings[col])
            self.products_tree.column(col, width=widths[col], anchor="w")
        self.products_tree.pack(fill="both", expand=True)

    def _build_sources_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="3. URLs y fuentes")

        upper = ttk.Panedwindow(tab, orient="horizontal")
        upper.pack(fill="both", expand=True)

        left = ttk.LabelFrame(upper, text="Producto", padding=8)
        right = ttk.LabelFrame(upper, text="URLs manuales prioritarias", padding=8)
        upper.add(left, weight=1)
        upper.add(right, weight=2)

        self.source_product_list = tk.Listbox(left, exportselection=False, height=10)
        self.source_product_list.pack(fill="both", expand=True)
        self.source_product_list.bind("<<ListboxSelect>>", self._on_source_product_select)

        ttk.Label(right, text="Una URL por línea. Son opcionales, pero se intentan primero y siempre pasan validación de identidad.").pack(anchor="w")
        self.urls_text = tk.Text(right, height=9, wrap="word", font=("Consolas", 9))
        self.urls_text.pack(fill="both", expand=True, pady=(5, 5))
        url_buttons = ttk.Frame(right)
        url_buttons.pack(fill="x")
        ttk.Button(url_buttons, text="Guardar URLs del producto", command=self.save_urls_for_selected).pack(side="left")
        ttk.Button(url_buttons, text="Preparar / ver fuentes a buscar", command=self.preview_sources).pack(side="left", padx=8)

        preview_box = ttk.LabelFrame(tab, text="Plan de búsqueda / fuentes candidatas", padding=8)
        preview_box.pack(fill="both", expand=True, pady=(10, 0))
        ttk.Label(
            preview_box,
            text="Orden real: URLs manuales → fabricante/soporte/PDF oficial → búsqueda gratuita → secundarias compatibles. Preparar fuentes NO extrae datos.",
        ).pack(anchor="w", pady=(0, 5))

        cols = ("priority", "type", "url", "status")
        self.sources_tree = ttk.Treeview(preview_box, columns=cols, show="headings", height=10)
        for col, title, width in [
            ("priority", "Prioridad", 80),
            ("type", "Tipo", 150),
            ("url", "Página que se intentará", 780),
            ("status", "Estado", 150),
        ]:
            self.sources_tree.heading(col, text=title)
            self.sources_tree.column(col, width=width, anchor="w")
        self.sources_tree.pack(fill="both", expand=True)

    def _build_attrs_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="4. Atributos Excel")
        ttk.Label(tab, text="Qué pide realmente esta plantilla", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(tab, text="Los campos STECH/marketplace pueden quedar vacíos. No bloquean el scraping y no se inventan.").pack(anchor="w", pady=(1, 7))

        attr_cols = ("column", "external_id", "label", "action", "required", "type", "options")
        self.attrs_tree = ttk.Treeview(tab, columns=attr_cols, show="headings", height=19)
        attr_headings = {
            "column": "Col.", "external_id": "ID", "label": "Atributo", "action": "Acción",
            "required": "Oblig.", "type": "Tipo", "options": "Opciones",
        }
        attr_widths = {"column": 55, "external_id": 90, "label": 330, "action": 220, "required": 70, "type": 120, "options": 75}
        for col in attr_cols:
            self.attrs_tree.heading(col, text=attr_headings[col])
            self.attrs_tree.column(col, width=attr_widths[col], anchor="w")
        yscroll = ttk.Scrollbar(tab, orient="vertical", command=self.attrs_tree.yview)
        self.attrs_tree.configure(yscrollcommand=yscroll.set)
        self.attrs_tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

    def _build_run_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="5. Ejecutar")

        out_box = ttk.LabelFrame(tab, text="Salida", padding=8)
        out_box.pack(fill="x")
        row = ttk.Frame(out_box)
        row.pack(fill="x")
        ttk.Label(row, text="Carpeta:").pack(side="left")
        self.out = tk.StringVar(value=str(Path.home() / "ProductIntelligence_Output"))
        ttk.Entry(row, textvariable=self.out).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="Elegir...", command=self.pick_out).pack(side="left")

        options = ttk.LabelFrame(tab, text="Configuración", padding=8)
        options.pack(fill="x", pady=(10, 0))
        self.overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options,
            text="Reinvestigar/sobrescribir datos de PRODUCTO existentes (seller/STECH sigue protegido)",
            variable=self.overwrite,
        ).pack(anchor="w")
        ttk.Label(options, text="No se inventan precio, stock, SKU vendedor ni otros datos propios de STECH/marketplace.", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(3, 0))

        summary_box = ttk.LabelFrame(tab, text="Resumen antes de ejecutar", padding=8)
        summary_box.pack(fill="both", expand=True, pady=(10, 0))
        self.run_summary = tk.Text(summary_box, height=12, wrap="word", font=("Consolas", 9), state="disabled")
        self.run_summary.pack(fill="both", expand=True)

        btns = ttk.Frame(tab)
        btns.pack(fill="x", pady=(10, 0))
        self.runbtn = ttk.Button(btns, text="INICIAR SCRAPING Y GENERAR EXCEL", command=self.run)
        self.runbtn.pack(side="left")
        ttk.Button(btns, text="Reprocesar JSON...", command=self.repair_jsons).pack(side="left", padx=8)
        ttk.Button(btns, text="Ver logs", command=lambda: self.notebook.select(self.logs_tab)).pack(side="left")

    def _build_logs_tab(self):
        self.logs_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.logs_tab, text="6. Logs / auditoría")
        ttk.Label(self.logs_tab, text="Proceso en vivo", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(
            self.logs_tab,
            text="Aquí verás cada URL probada, método de extracción, validación de identidad, evidencias encontradas y motivo de rechazo/aceptación.",
        ).pack(anchor="w", pady=(1, 6))
        self.log = tk.Text(self.logs_tab, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        self.log.insert("end", "Listo. Primero analiza la plantilla.\n")
        buttons = ttk.Frame(self.logs_tab)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Limpiar logs", command=lambda: self.log.delete("1.0", "end")).pack(side="left")
        ttk.Button(buttons, text="Abrir carpeta de salida", command=self.open_output_folder).pack(side="left", padx=8)

    def pick_excel(self):
        p = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if p:
            self.excel.set(p)
            self.out.set(str(Path(p).parent / (Path(p).stem + "_salida")))
            self.analyze_excel()

    def pick_out(self):
        p = filedialog.askdirectory()
        if p:
            self.out.set(p)
            self._refresh_run_summary()

    def open_output_folder(self):
        p = Path(self.out.get())
        p.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(p))
        except Exception:
            messagebox.showinfo("Carpeta de salida", str(p))

    def emit(self, msg):
        self.q.put(str(msg))

    def _drain(self):
        try:
            while True:
                m = self.q.get_nowait()
                self.log.insert("end", m + "\n")
                self.log.see("end")
        except queue.Empty:
            pass
        self.after(150, self._drain)

    def _clear_tree(self, tree):
        for item in tree.get_children():
            tree.delete(item)

    def _identity_for_index(self, index: int) -> ProductIdentity | None:
        if index < 0 or index >= len(self.product_rows):
            return None
        p = self.product_rows[index]
        ident = parse_product_query(str(p.get("identifier") or p.get("model") or p.get("product_name") or ""))
        if ident is None:
            return None
        # Preserve useful hints detected from Excel without making them mandatory.
        updates = {}
        if p.get("brand") and not ident.brand:
            updates["brand"] = p.get("brand")
        if p.get("model") and not ident.model:
            updates["model"] = p.get("model")
        return ident.model_copy(update=updates) if updates else ident

    def analyze_excel(self):
        template = self.excel.get().strip()
        if not template or not Path(template).exists():
            messagebox.showerror("Falta archivo", "Selecciona una plantilla .xlsx.")
            return
        try:
            data = analyze_workbook(template)
            self.preflight = data
            self.product_rows = list(data.get("products") or [])
            self.manual_urls = {i: list(p.get("source_urls") or []) for i, p in enumerate(self.product_rows)}
            self.source_preview = {}
            self._clear_tree(self.products_tree)
            self._clear_tree(self.attrs_tree)
            self._clear_tree(self.sources_tree)
            self.source_product_list.delete(0, "end")

            for i, p in enumerate(self.product_rows):
                self.products_tree.insert("", "end", iid=str(i), values=(
                    p.get("row"), p.get("identifier") or "", p.get("brand") or "",
                    p.get("model") or p.get("product_name") or "", len(self.manual_urls.get(i, [])), "Listo para revisar",
                ))
                self.source_product_list.insert("end", p.get("identifier") or p.get("model") or p.get("product_name") or f"Producto {i+1}")

            for f in data["attributes"]:
                self.attrs_tree.insert("", "end", values=(
                    f.get("column"), f.get("external_id") or "", f.get("label") or "", f.get("action") or "",
                    "Sí" if f.get("required") else "No", f.get("value_type") or "", f.get("options_count") or 0,
                ))

            if self.product_rows:
                self.source_product_list.selection_set(0)
                self._on_source_product_select()

            s = data["summary"]
            actions = s.get("actions", {})
            self.analysis_status.set(
                f"Detectado: {s.get('products_detected', 0)} productos | {s.get('fields_total', 0)} campos | "
                f"{actions.get('INVESTIGAR', 0)} investigar | {actions.get('VALIDAR / COMPLETAR', 0)} identidad | "
                f"{actions.get('IMAGEN', 0)} imágenes | {actions.get('DEJAR VACÍO / PROTEGER', 0)} STECH/marketplace"
            )
            self.emit("=== ANÁLISIS DEL EXCEL ===")
            self.emit(json.dumps(s, ensure_ascii=False))
            self._refresh_run_summary()
        except Exception as e:
            self.preflight = None
            self.analysis_status.set("No se pudo analizar la plantilla.")
            self.emit(traceback.format_exc())
            messagebox.showerror("Error al analizar Excel", str(e))

    def _selected_source_index(self) -> int | None:
        sel = self.source_product_list.curselection()
        return int(sel[0]) if sel else None

    def _on_source_product_select(self, _event=None):
        index = self._selected_source_index()
        if index is None:
            return
        self.urls_text.delete("1.0", "end")
        self.urls_text.insert("1.0", "\n".join(self.manual_urls.get(index, [])))
        self._render_source_preview(index)

    def save_urls_for_selected(self):
        index = self._selected_source_index()
        if index is None:
            messagebox.showwarning("Producto", "Selecciona primero un producto.")
            return
        urls = []
        for line in self.urls_text.get("1.0", "end").splitlines():
            value = line.strip()
            if value and value not in urls:
                urls.append(value)
        self.manual_urls[index] = urls
        if self.products_tree.exists(str(index)):
            values = list(self.products_tree.item(str(index), "values"))
            values[4] = len(urls)
            values[5] = "Con URLs manuales" if urls else "Discovery automático"
            self.products_tree.item(str(index), values=values)
        self._refresh_run_summary()
        self.emit(f"URLs guardadas para producto {index+1}: {len(urls)}")

    def preview_sources(self):
        index = self._selected_source_index()
        if index is None:
            messagebox.showwarning("Producto", "Selecciona primero un producto.")
            return
        self.save_urls_for_selected()
        ident = self._identity_for_index(index)
        if ident is None:
            messagebox.showerror("Identidad", "No se pudo interpretar el identificador del producto.")
            return

        self._clear_tree(self.sources_tree)
        manual = self.manual_urls.get(index, [])
        for pos, url in enumerate(manual, 1):
            self.sources_tree.insert("", "end", values=(pos, "Manual prioritaria", url, "Se intentará primero"))

        def work():
            try:
                self.emit(f"Preparando fuentes para: {ident.mpn or ident.ean or ident.upc or ident.gtin or ident.model or ident.product_name}")
                found = search_web(ident, limit=12)
                rows = []
                seen = set(manual)
                priority = len(manual) + 1
                for candidate in found:
                    if candidate.url in seen:
                        continue
                    seen.add(candidate.url)
                    source_type = "Oficial probable" if getattr(candidate, "likely_official", False) else "Discovery gratuito"
                    rows.append({"priority": priority, "type": source_type, "url": candidate.url, "status": "Candidata; pendiente validar identidad"})
                    priority += 1
                self.source_preview[index] = rows
                self.after(0, lambda: self._render_source_preview(index))
                self.emit(f"Fuentes candidatas preparadas: {len(rows)} + {len(manual)} manuales")
            except Exception:
                self.emit(traceback.format_exc())

        threading.Thread(target=work, daemon=True).start()

    def _render_source_preview(self, index: int):
        self._clear_tree(self.sources_tree)
        priority = 1
        for url in self.manual_urls.get(index, []):
            self.sources_tree.insert("", "end", values=(priority, "Manual prioritaria", url, "Se intentará primero"))
            priority += 1
        for row in self.source_preview.get(index, []):
            self.sources_tree.insert("", "end", values=(row["priority"], row["type"], row["url"], row["status"]))

    def _entries(self):
        identities = []
        urls = []
        for i in range(len(self.product_rows)):
            ident = self._identity_for_index(i)
            if ident:
                identities.append(ident)
                urls.append(list(self.manual_urls.get(i, [])))
        return identities, urls

    def _refresh_run_summary(self):
        if not hasattr(self, "run_summary"):
            return
        products = len(self.product_rows)
        manual_count = sum(len(v) for v in self.manual_urls.values())
        attrs = (self.preflight or {}).get("summary", {})
        actions = attrs.get("actions", {})
        text = (
            f"Productos: {products}\n"
            f"URLs manuales: {manual_count}\n"
            f"Campos a investigar: {actions.get('INVESTIGAR', 0)}\n"
            f"Campos de identidad: {actions.get('VALIDAR / COMPLETAR', 0)}\n"
            f"Imágenes: {actions.get('IMAGEN', 0)}\n"
            f"STECH/marketplace protegidos: {actions.get('DEJAR VACÍO / PROTEGER', 0)}\n"
            f"Salida: {self.out.get()}\n\n"
            "Durante la ejecución se registrará cada URL probada, si fue aceptada/rechazada y qué método/evidencia produjo."
        )
        self.run_summary.configure(state="normal")
        self.run_summary.delete("1.0", "end")
        self.run_summary.insert("1.0", text)
        self.run_summary.configure(state="disabled")

    def run(self):
        if not self.excel.get() or not Path(self.excel.get()).exists():
            messagebox.showerror("Falta archivo", "Selecciona una plantilla .xlsx.")
            return
        if self.preflight is None:
            self.analyze_excel()
            if self.preflight is None:
                return

        index = self._selected_source_index()
        if index is not None:
            self.save_urls_for_selected()
        identities, source_urls = self._entries()
        self.runbtn.configure(state="disabled")
        self.notebook.select(self.logs_tab)

        def work():
            try:
                self.emit("=== INICIO SCRAPING ===")
                self.emit("Orden: manuales → discovery/fabricante → validación identidad → extracción → resolución → Excel")
                for i, ident in enumerate(identities, 1):
                    self.emit(f"Producto {i}: {json.dumps({k:v for k,v in ident.model_dump().items() if v not in (None, '')}, ensure_ascii=False)}")
                    for url in source_urls[i-1]:
                        self.emit(f"  URL manual prioritaria: {url}")
                res = run_batch(
                    self.excel.get(), self.out.get(), overwrite=self.overwrite.get(), log=self.emit,
                    manual_identities=identities or None, manual_source_urls=source_urls or None,
                )
                self.emit(json.dumps(res, ensure_ascii=False, indent=2))
                self.emit("=== TERMINADO ===")
                self.after(0, lambda: messagebox.showinfo(
                    "Terminado",
                    f"Excel: {res['output_excel']}\nTrazabilidad: {res['trace']}\nResolución: {res.get('resolution')}\nResumen: {Path(self.out.get()) / 'resumen.json'}",
                ))
            except Exception as e:
                self.emit(traceback.format_exc())
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: self.runbtn.configure(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    def repair_jsons(self):
        files = filedialog.askopenfilenames(filetypes=[("JSON", "*.json")])
        if not files:
            return
        template = self.excel.get()
        if not template or not Path(template).exists():
            messagebox.showerror("Falta plantilla", "Selecciona primero el Excel a completar.")
            return
        out = Path(self.out.get())
        out.mkdir(parents=True, exist_ok=True)
        try:
            recs = [repair_existing_record(ProductRecord.model_validate_json(Path(p).read_text(encoding="utf-8"))) for p in files]
            dest = out / (Path(template).stem + "_reprocesado.xlsx")
            trace = out / "trazabilidad_reprocesado.json"
            rep = fill_excel_v8(template, str(dest), recs, overwrite=self.overwrite.get(), trace_path=str(trace))
            self.emit(f"Reprocesado: {dest}")
            self.emit(json.dumps(rep["summary"], ensure_ascii=False))
            messagebox.showinfo("Reprocesado", str(dest))
        except Exception as e:
            self.emit(traceback.format_exc())
            messagebox.showerror("Error", str(e))


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
