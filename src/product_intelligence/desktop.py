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
from .excel_mapper_v8 import fill_excel_v8
from .input_identity import parse_product_entries
from .models import ProductRecord
from .preflight import analyze_workbook
from .repair import repair_existing_record


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Product Intelligence — Excel + Scraping web sin IA")
        self.geometry("1260x920")
        self.minsize(1050, 720)
        self.q = queue.Queue()
        self.preflight = None
        self._build()
        self.after(150, self._drain)

    def _build(self):
        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Product Intelligence", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(
            main,
            text="El Excel define qué investigar. Primero revisa productos y atributos; luego el scraper completa solo lo verificable.",
        ).pack(anchor="w", pady=(2, 8))

        top = ttk.LabelFrame(main, text="1. Plantilla Excel", padding=8)
        top.pack(fill="x")
        self.excel = tk.StringVar()
        ttk.Entry(top, textvariable=self.excel).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Elegir...", command=self.pick_excel).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="ANALIZAR EXCEL", command=self.analyze_excel).pack(side="left", padx=(8, 0))

        self.analysis_status = tk.StringVar(value="Selecciona un Excel y pulsa ANALIZAR EXCEL.")
        ttk.Label(main, textvariable=self.analysis_status, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(6, 4))

        notebook = ttk.Notebook(main)
        notebook.pack(fill="both", expand=True)

        # Products / URLs tab
        products_tab = ttk.Frame(notebook, padding=8)
        notebook.add(products_tab, text="Productos y URLs")

        cols = ("row", "identifier", "brand", "model", "urls")
        self.products_tree = ttk.Treeview(products_tab, columns=cols, show="headings", height=8)
        headings = {
            "row": "Fila",
            "identifier": "Identificador principal",
            "brand": "Marca",
            "model": "Modelo",
            "urls": "URLs detectadas",
        }
        widths = {"row": 60, "identifier": 260, "brand": 130, "model": 280, "urls": 130}
        for col in cols:
            self.products_tree.heading(col, text=headings[col])
            self.products_tree.column(col, width=widths[col], anchor="w")
        self.products_tree.pack(fill="x")

        entry_box = ttk.LabelFrame(
            products_tab,
            text="Entradas a procesar / URLs prioritarias (opcional)",
            padding=8,
        )
        entry_box.pack(fill="x", pady=(8, 0))
        self.product_queries = tk.Text(entry_box, height=7, wrap="word", font=("Consolas", 10))
        self.product_queries.pack(fill="x")
        ttk.Label(
            entry_box,
            text="Una línea por producto. Basta MPN, EAN, UPC/GTIN o nombre. Puedes añadir varias: | url=https://... | url=https://...",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            entry_box,
            text="Al analizar el Excel, esta caja se llena automáticamente con los identificadores detectados. Tú solo agregas URLs si las tienes.",
        ).pack(anchor="w")

        # Attributes tab
        attrs_tab = ttk.Frame(notebook, padding=8)
        notebook.add(attrs_tab, text="Atributos requeridos por el Excel")
        attr_cols = ("column", "external_id", "label", "action", "required", "type", "options")
        self.attrs_tree = ttk.Treeview(attrs_tab, columns=attr_cols, show="headings", height=17)
        attr_headings = {
            "column": "Col.",
            "external_id": "ID",
            "label": "Atributo",
            "action": "Qué hará el sistema",
            "required": "Oblig.",
            "type": "Tipo",
            "options": "Opciones",
        }
        attr_widths = {"column": 55, "external_id": 90, "label": 300, "action": 190, "required": 70, "type": 115, "options": 70}
        for col in attr_cols:
            self.attrs_tree.heading(col, text=attr_headings[col])
            self.attrs_tree.column(col, width=attr_widths[col], anchor="w")
        yscroll = ttk.Scrollbar(attrs_tab, orient="vertical", command=self.attrs_tree.yview)
        self.attrs_tree.configure(yscrollcommand=yscroll.set)
        self.attrs_tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        # Run controls
        controls = ttk.LabelFrame(main, text="2. Ejecución", padding=8)
        controls.pack(fill="x", pady=(8, 0))

        out_row = ttk.Frame(controls)
        out_row.pack(fill="x")
        ttk.Label(out_row, text="Carpeta de salida:").pack(side="left")
        self.out = tk.StringVar(value=str(Path.home() / "ProductIntelligence_Output"))
        ttk.Entry(out_row, textvariable=self.out).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(out_row, text="Elegir...", command=self.pick_out).pack(side="left")

        self.overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            controls,
            text="Reinvestigar/sobrescribir datos de PRODUCTO existentes. Precio, stock, SKU vendedor y otros datos STECH no se inventan.",
            variable=self.overwrite,
        ).pack(anchor="w", pady=(7, 2))
        ttk.Label(
            controls,
            text="Los campos que dependen de STECH/marketplace pueden quedar vacíos; nunca bloquean el scraping ni se rellenan con suposiciones.",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            controls,
            text="Fuentes: URLs manuales → fabricante/ficha técnica/PDF/soporte → búsqueda gratuita → secundarias compatibles. Sin IA ni API key.",
        ).pack(anchor="w", pady=(2, 6))

        btns = ttk.Frame(controls)
        btns.pack(fill="x")
        self.runbtn = ttk.Button(btns, text="EJECUTAR SCRAPING Y GENERAR EXCEL", command=self.run)
        self.runbtn.pack(side="left")
        ttk.Button(btns, text="Reprocesar JSON...", command=self.repair_jsons).pack(side="left", padx=8)

        audit = ttk.LabelFrame(main, text="Actividad / auditoría", padding=6)
        audit.pack(fill="both", expand=False, pady=(8, 0))
        self.log = tk.Text(audit, height=10, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        self.log.insert("end", "Listo. Primero analiza la plantilla.\n")

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

    def analyze_excel(self):
        template = self.excel.get().strip()
        if not template or not Path(template).exists():
            messagebox.showerror("Falta archivo", "Selecciona una plantilla .xlsx.")
            return
        try:
            data = analyze_workbook(template)
            self.preflight = data
            self._clear_tree(self.products_tree)
            self._clear_tree(self.attrs_tree)

            for p in data["products"]:
                self.products_tree.insert(
                    "", "end",
                    values=(
                        p.get("row"),
                        p.get("identifier") or "",
                        p.get("brand") or "",
                        p.get("model") or p.get("product_name") or "",
                        len(p.get("source_urls") or []),
                    ),
                )

            for f in data["attributes"]:
                self.attrs_tree.insert(
                    "", "end",
                    values=(
                        f.get("column"),
                        f.get("external_id") or "",
                        f.get("label") or "",
                        f.get("action") or "",
                        "Sí" if f.get("required") else "No",
                        f.get("value_type") or "",
                        f.get("options_count") or 0,
                    ),
                )

            # Seed the editable product/URL area only when empty. This preserves user URLs on re-analysis.
            if not self.product_queries.get("1.0", "end").strip() and data["products"]:
                lines = [p["identifier"] for p in data["products"] if p.get("identifier")]
                self.product_queries.insert("1.0", "\n".join(lines))

            s = data["summary"]
            actions = s.get("actions", {})
            self.analysis_status.set(
                f"Detectado: {s.get('products_detected', 0)} productos | {s.get('fields_total', 0)} campos | "
                f"{actions.get('INVESTIGAR', 0)} investigar | {actions.get('VALIDAR / COMPLETAR', 0)} identidad | "
                f"{actions.get('IMAGEN', 0)} imágenes | {actions.get('DEJAR VACÍO / PROTEGER', 0)} STECH/marketplace"
            )
            self.emit("=== ANÁLISIS DEL EXCEL ===")
            self.emit(json.dumps(s, ensure_ascii=False))
            if data.get("reference_sheets"):
                self.emit("Hojas de referencia (no se scrapean como producto): " + ", ".join(data["reference_sheets"]))
        except Exception as e:
            self.preflight = None
            self.analysis_status.set("No se pudo analizar la plantilla.")
            self.emit(traceback.format_exc())
            messagebox.showerror("Error al analizar Excel", str(e))

    def _manual_entries(self):
        return parse_product_entries(self.product_queries.get("1.0", "end").strip())

    def run(self):
        if not self.excel.get() or not Path(self.excel.get()).exists():
            messagebox.showerror("Falta archivo", "Selecciona una plantilla .xlsx.")
            return
        if self.preflight is None:
            self.analyze_excel()
            if self.preflight is None:
                return

        entries = self._manual_entries()
        identities = [e.identity for e in entries]
        source_urls = [e.source_urls for e in entries]
        self.runbtn.configure(state="disabled")

        def work():
            try:
                self.emit("=== INICIO SCRAPING ===")
                self.emit("Sin IA. Datos STECH/marketplace pueden permanecer vacíos.")
                if identities:
                    for i, x in enumerate(identities, 1):
                        urls = source_urls[i - 1] if i - 1 < len(source_urls) else []
                        self.emit(
                            f"Entrada {i}: "
                            + json.dumps(
                                {**{k: v for k, v in x.model_dump().items() if v not in (None, "")}, "urls": urls},
                                ensure_ascii=False,
                            )
                        )
                res = run_batch(
                    self.excel.get(),
                    self.out.get(),
                    overwrite=self.overwrite.get(),
                    log=self.emit,
                    manual_identities=identities or None,
                    manual_source_urls=source_urls or None,
                )
                self.emit(json.dumps(res, ensure_ascii=False, indent=2))
                self.emit("=== TERMINADO ===")
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Terminado",
                        f"Excel: {res['output_excel']}\nTrazabilidad: {res['trace']}\nResumen: {Path(self.out.get()) / 'resumen.json'}",
                    ),
                )
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
            recs = [
                repair_existing_record(ProductRecord.model_validate_json(Path(p).read_text(encoding="utf-8")))
                for p in files
            ]
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
