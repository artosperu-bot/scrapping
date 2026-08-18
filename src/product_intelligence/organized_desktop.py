from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .progress_animation import ProgressAnimation
from .workspace_desktop import App as WorkspaceApp
from .workspace_management import delete_workspace_record
from .workspace_paths import (
    clean_workspace_results,
    default_jobs_root,
    delete_workspace_files,
    ensure_workspace_layout,
    workspace_dir,
)


class App(WorkspaceApp):
    """Final presentation/management shell; existing processing engines stay inherited."""

    def __init__(self):
        self._jobs_root = default_jobs_root()
        self._active_workspace_path: Path | None = None
        super().__init__()

    # ---------- Multimedia presentation ----------
    def _build_media_tab(self):
        super()._build_media_tab()
        for child in list(self.media_tab.winfo_children()):
            child.destroy()

        ttk.Label(self.media_tab, text="Multimedia por producto", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(self.media_tab, text="Buscar, revisar galería y auditar en vistas separadas. El motor multimedia no cambia.").pack(anchor="w", pady=(1, 7))
        self.media_views = ttk.Notebook(self.media_tab)
        self.media_views.pack(fill="both", expand=True)
        search_tab = ttk.Frame(self.media_views, padding=8)
        gallery_tab = ttk.Frame(self.media_views, padding=8)
        audit_tab = ttk.Frame(self.media_views, padding=8)
        self.media_views.add(search_tab, text="Buscar")
        self.media_views.add(gallery_tab, text="Galería")
        self.media_views.add(audit_tab, text="Auditoría")

        upper = ttk.Panedwindow(search_tab, orient="horizontal")
        upper.pack(fill="x")
        left = ttk.LabelFrame(upper, text="Producto", padding=8)
        right = ttk.LabelFrame(upper, text="URLs manuales opcionales", padding=8)
        upper.add(left, weight=1)
        upper.add(right, weight=2)
        self.media_product_list = tk.Listbox(left, exportselection=False, height=7)
        self.media_product_list.pack(fill="both", expand=True)
        self.media_product_list.bind("<<ListboxSelect>>", self._on_media_product_select)
        ttk.Label(right, text="Una URL por línea. Se valida siempre contra el producto.").pack(anchor="w")
        self.media_urls_text = tk.Text(right, height=4, wrap="word", font=("Consolas", 9))
        self.media_urls_text.pack(fill="both", expand=True, pady=(4, 5))
        controls = ttk.Frame(right); controls.pack(fill="x")
        self.media_auto_search = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Buscar automáticamente por Part Number/modelo", variable=self.media_auto_search).pack(side="left")
        ttk.Button(controls, text="Guardar URLs", command=self._save_media_urls).pack(side="right")

        action_row = ttk.Frame(search_tab); action_row.pack(fill="x", pady=(8, 5))
        self.media_selected_btn = ttk.Button(action_row, text="BUSCAR Y DESCARGAR MULTIMEDIA", command=self._run_media_selected)
        self.media_selected_btn.pack(side="left")
        self.media_all_btn = ttk.Button(action_row, text="Procesar todos", command=self._run_media_all)
        self.media_all_btn.pack(side="left", padx=8)
        ttk.Button(action_row, text="Abrir carpeta multimedia", command=self._open_media_folder).pack(side="left")
        self.media_status = tk.StringVar(value="Analiza un Excel para cargar los productos.")
        ttk.Label(action_row, textvariable=self.media_status, font=("Segoe UI", 9, "bold")).pack(side="left", padx=12)

        progress_box = ttk.LabelFrame(search_tab, text="Progreso", padding=10, height=185)
        progress_box.pack_propagate(False); progress_box.pack(fill="x", pady=(8, 0))
        pleft = ttk.Frame(progress_box); pleft.pack(side="left", fill="both", expand=True, padx=(0, 12))
        pright = ttk.Frame(progress_box); pright.pack(side="right", fill="y")
        self.media_progress_title = tk.StringVar(value="Listo para buscar multimedia")
        ttk.Label(pleft, textvariable=self.media_progress_title, font=("Segoe UI", 10, "bold"), wraplength=720).pack(anchor="w")
        row1 = ttk.Frame(pleft); row1.pack(fill="x", pady=(8, 3)); ttk.Label(row1, text="Producto actual", width=16).pack(side="left")
        self.media_product_progress = ttk.Progressbar(row1, maximum=100); self.media_product_progress.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self.media_product_percent = tk.StringVar(value="0%"); ttk.Label(row1, textvariable=self.media_product_percent, width=9).pack(side="left")
        row2 = ttk.Frame(pleft); row2.pack(fill="x", pady=3); ttk.Label(row2, text="Progreso general", width=16).pack(side="left")
        self.media_overall_progress = ttk.Progressbar(row2, maximum=100); self.media_overall_progress.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self.media_overall_percent = tk.StringVar(value="0%"); ttk.Label(row2, textvariable=self.media_overall_percent, width=9).pack(side="left")
        self.media_progress_detail = tk.StringVar(value="0 productos completados")
        ttk.Label(pleft, textvariable=self.media_progress_detail).pack(anchor="w", pady=(6, 0))
        self.media_progress_animation = ProgressAnimation(pright, width=220, height=140); self.media_progress_animation.pack()

        gallery_box = ttk.LabelFrame(gallery_tab, text="Imágenes y videos encontrados", padding=5)
        gallery_box.pack(fill="both", expand=True)
        self.media_canvas = tk.Canvas(gallery_box, highlightthickness=0)
        scroll = ttk.Scrollbar(gallery_box, orient="vertical", command=self.media_canvas.yview)
        self.media_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y"); self.media_canvas.pack(side="left", fill="both", expand=True)
        self.media_gallery = ttk.Frame(self.media_canvas)
        self._media_window = self.media_canvas.create_window((0, 0), window=self.media_gallery, anchor="nw")
        self.media_gallery.bind("<Configure>", lambda _e: self.media_canvas.configure(scrollregion=self.media_canvas.bbox("all")))
        self.media_canvas.bind("<Configure>", lambda e: self.media_canvas.itemconfigure(self._media_window, width=e.width))
        self.media_gallery_box = gallery_box

        columns = ("time", "type", "status", "detail")
        self.media_audit_tree = ttk.Treeview(audit_tab, columns=columns, show="headings")
        for col, title, width in (("time", "Hora", 90), ("type", "Evento", 150), ("status", "Estado", 160), ("detail", "Detalle", 760)):
            self.media_audit_tree.heading(col, text=title); self.media_audit_tree.column(col, width=width, anchor="w")
        sb = ttk.Scrollbar(audit_tab, orient="vertical", command=self.media_audit_tree.yview)
        self.media_audit_tree.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y"); self.media_audit_tree.pack(side="left", fill="both", expand=True)

    def _apply_progress_event(self, event: dict):
        tree = getattr(self, "media_audit_tree", None)
        if tree is not None:
            kind = str(event.get("type") or "")
            status = str(event.get("status") or "")
            detail = str(event.get("message") or event.get("url") or event.get("error") or event.get("reason") or "")
            tree.insert("", "end", values=(datetime.now().strftime("%H:%M:%S"), kind, status, detail[:900]))
        return super()._apply_progress_event(event)

    # ---------- Price presentation ----------
    def _build_price_tab(self):
        super()._build_price_tab()
        for child in list(self.price_tab.winfo_children()):
            child.destroy()

        ttk.Label(self.price_tab, text="Inteligencia de precios", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(self.price_tab, text="Búsqueda, ofertas, cobertura y auditoría separadas. El motor de precios no cambia.").pack(anchor="w", pady=(1, 7))
        self.price_results_notebook = ttk.Notebook(self.price_tab)
        self.price_results_notebook.pack(fill="both", expand=True)
        search_tab = ttk.Frame(self.price_results_notebook, padding=8)
        offers_tab = ttk.Frame(self.price_results_notebook, padding=5)
        coverage_tab = ttk.Frame(self.price_results_notebook, padding=5)
        audit_tab = ttk.Frame(self.price_results_notebook, padding=5)
        self.price_results_notebook.add(search_tab, text="Buscar")
        self.price_results_notebook.add(offers_tab, text="Ofertas")
        self.price_results_notebook.add(coverage_tab, text="Cobertura")
        self.price_results_notebook.add(audit_tab, text="Auditoría")

        top = ttk.Panedwindow(search_tab, orient="horizontal"); top.pack(fill="x")
        left = ttk.LabelFrame(top, text="Productos detectados", padding=10)
        right = ttk.LabelFrame(top, text="Acciones y estado", padding=10)
        top.add(left, weight=1); top.add(right, weight=2)

        ttk.Label(left, text="Part Number / MPN").pack(anchor="w")
        manual_row = ttk.Frame(left)
        manual_row.pack(fill="x", pady=(2, 6))
        manual_entry = ttk.Entry(manual_row, textvariable=self.price_manual_part_number, width=24)
        manual_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(manual_row, text="Agregar", command=self._add_manual_price_product).pack(side="left", padx=(5, 0))
        manual_entry.bind("<Return>", lambda _event: self._add_manual_price_product())

        self.price_product_list = tk.Listbox(left, exportselection=False, height=8)
        self.price_product_list.pack(fill="both", expand=True)
        actions = ttk.Frame(right); actions.pack(fill="x")
        self.price_selected_btn = ttk.Button(actions, text="BUSCAR PRECIOS", command=self._run_price_selected); self.price_selected_btn.pack(side="left")
        self.price_all_btn = ttk.Button(actions, text="Procesar todos", command=self._run_price_all); self.price_all_btn.pack(side="left", padx=(8, 0))
        self.price_status = tk.StringVar(value="Analiza un Excel o agrega un Part Number para buscar precios.")
        ttk.Label(right, textvariable=self.price_status, wraplength=720, justify="left").pack(anchor="w", fill="x", pady=(10, 0))

        progress = ttk.LabelFrame(search_tab, text="Progreso", padding=10, height=190); progress.pack(fill="x", pady=(10, 6)); progress.pack_propagate(False)
        pleft = ttk.Frame(progress); pleft.pack(side="left", fill="both", expand=True, padx=(0, 12))
        pright = ttk.Frame(progress); pright.pack(side="right", fill="y")
        row1 = ttk.Frame(pleft); row1.pack(fill="x", pady=(10, 5)); ttk.Label(row1, text="Producto actual", width=16).pack(side="left")
        self.price_product_progress = ttk.Progressbar(row1, maximum=100); self.price_product_progress.pack(side="left", fill="x", expand=True, padx=(6, 8))
        self.price_product_percent = tk.StringVar(value="0%"); ttk.Label(row1, textvariable=self.price_product_percent, width=9).pack(side="left")
        row2 = ttk.Frame(pleft); row2.pack(fill="x"); ttk.Label(row2, text="Progreso general", width=16).pack(side="left")
        self.price_overall_progress = ttk.Progressbar(row2, maximum=100); self.price_overall_progress.pack(side="left", fill="x", expand=True, padx=(6, 8))
        self.price_overall_percent = tk.StringVar(value="0%"); ttk.Label(row2, textvariable=self.price_overall_percent, width=9).pack(side="left")
        self.price_progress_animation = ProgressAnimation(pright, width=220, height=140); self.price_progress_animation.pack()
        self.price_summary = tk.StringVar(value="Sin resultados todavía.")
        ttk.Label(search_tab, textvariable=self.price_summary, font=("Segoe UI", 9, "bold"), wraplength=1100, justify="left").pack(anchor="w", fill="x", pady=(4, 0))

        columns = ("product", "channel", "seller", "price", "list_price", "stock", "confidence", "url")
        self.price_tree = ttk.Treeview(offers_tab, columns=columns, show="headings", selectmode="browse")
        headings = {"product":"Producto","channel":"Canal","seller":"Vendedor","price":"Precio","list_price":"Precio lista","stock":"Stock","confidence":"Conf.","url":"Enlace"}
        widths = {"product":150,"channel":110,"seller":160,"price":105,"list_price":105,"stock":70,"confidence":70,"url":280}
        for col in columns:
            self.price_tree.heading(col, text=headings[col]); self.price_tree.column(col, width=widths[col], anchor="w")
        sb = ttk.Scrollbar(offers_tab, orient="vertical", command=self.price_tree.yview); self.price_tree.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y"); self.price_tree.pack(side="left", fill="both", expand=True)
        self.price_tree.bind("<Double-1>", self._open_price_offer)

        coverage_columns = ("channel", "status", "offers", "detail")
        self.price_coverage_tree = ttk.Treeview(coverage_tab, columns=coverage_columns, show="headings")
        for col, title, width in (("channel","Canal",180),("status","Estado",110),("offers","Ofertas",80),("detail","Detalle",650)):
            self.price_coverage_tree.heading(col, text=title); self.price_coverage_tree.column(col, width=width, anchor="w")
        sb2 = ttk.Scrollbar(coverage_tab, orient="vertical", command=self.price_coverage_tree.yview); self.price_coverage_tree.configure(yscrollcommand=sb2.set); sb2.pack(side="right", fill="y"); self.price_coverage_tree.pack(side="left", fill="both", expand=True)

        audit_columns = ("time", "stage", "source", "status", "detail")
        self.price_audit_tree = ttk.Treeview(audit_tab, columns=audit_columns, show="headings")
        for col, title, width in (("time","Hora",90),("stage","Etapa",130),("source","Fuente",160),("status","Estado",110),("detail","Detalle",680)):
            self.price_audit_tree.heading(col, text=title); self.price_audit_tree.column(col, width=width, anchor="w")
        sb3 = ttk.Scrollbar(audit_tab, orient="vertical", command=self.price_audit_tree.yview); self.price_audit_tree.configure(yscrollcommand=sb3.set); sb3.pack(side="right", fill="y"); self.price_audit_tree.pack(side="left", fill="both", expand=True)

    # ---------- Workspace management ----------
    def _install_workspace_page(self):
        super()._install_workspace_page()
        management = ttk.Frame(self.workspaces_tab, style="Page.TFrame")
        management.pack(fill="x", pady=(8, 0), before=self.workspaces_tab.winfo_children()[-1] if self.workspaces_tab.winfo_children() else None)
        ttk.Button(management, text="Abrir carpeta", command=self._open_workspace_folder).pack(side="left")
        ttk.Button(management, text="Limpiar resultados", command=self._clean_selected_workspace).pack(side="left", padx=(8, 0))
        ttk.Button(management, text="Eliminar trabajo", command=self._delete_selected_workspace).pack(side="left", padx=(8, 0))
        ttk.Button(management, text="Eliminar trabajo y archivos...", command=self._delete_selected_workspace_with_files).pack(side="left", padx=(8, 0))

    def _workspace_busy(self) -> bool:
        return bool(
            getattr(self, "_workspace_core_active", False)
            or getattr(self, "_workspace_media_active", False)
            or getattr(self, "_workspace_price_active", False)
            or getattr(self, "_media_running", False)
            or getattr(self, "_price_running", False)
        )

    def _workspace_path_for(self, workspace_id: str) -> Path:
        if self._workspace_repo is None:
            raise RuntimeError("Workspace repository is not ready")
        workspace = self._workspace_repo.get_workspace(workspace_id)
        return workspace_dir(self._jobs_root, workspace.id, workspace.name)

    def _activate_workspace_storage(self, workspace_id: str) -> Path:
        if self._workspace_repo is None:
            raise RuntimeError("Workspace repository is not ready")
        workspace = self._workspace_repo.get_workspace(workspace_id)
        layout = ensure_workspace_layout(self._jobs_root, workspace.id, workspace.name)
        self._active_workspace_path = layout["root"]
        if hasattr(self, "out"):
            self.out.set(str(layout["root"]))
            self._refresh_run_summary()
        return layout["root"]

    def _create_workspace(self):
        super()._create_workspace()
        if self._active_workspace_id:
            path = self._activate_workspace_storage(self._active_workspace_id)
            self.workspace_status.set(f"Trabajo activo · carpeta: {path}")

    def _open_selected_workspace(self):
        selected = self._workspace_selected_id
        super()._open_selected_workspace()
        if selected and self._active_workspace_id == selected:
            path = self._activate_workspace_storage(selected)
            if hasattr(self, "global_status"):
                self.global_status.set(f"Trabajo activo · {path.name}")

    def _open_workspace_folder(self):
        workspace_id = self._workspace_selected_id or self._active_workspace_id
        if not workspace_id:
            messagebox.showinfo("Trabajos", "Selecciona un trabajo.")
            return
        path = self._activate_workspace_storage(workspace_id)
        try:
            os.startfile(str(path))
        except Exception:
            messagebox.showinfo("Carpeta del trabajo", str(path))

    def _clean_selected_workspace(self):
        workspace_id = self._workspace_selected_id or self._active_workspace_id
        if not workspace_id:
            messagebox.showinfo("Trabajos", "Selecciona un trabajo.")
            return
        if self._workspace_busy():
            messagebox.showwarning("Trabajos", "No se puede limpiar mientras existe un proceso en ejecución.")
            return
        path = self._workspace_path_for(workspace_id)
        if not messagebox.askyesno("Limpiar resultados", "Se eliminarán los resultados generados de este trabajo. El trabajo y la carpeta Excel se conservarán. ¿Continuar?"):
            return
        clean_workspace_results(path)
        self.workspace_status.set("Resultados limpiados. Trabajo y Excel conservados.")

    def _delete_selected_workspace(self):
        workspace_id = self._workspace_selected_id
        if not workspace_id or self._workspace_repo is None:
            messagebox.showinfo("Trabajos", "Selecciona un trabajo.")
            return
        if self._workspace_busy():
            messagebox.showwarning("Trabajos", "No se puede eliminar mientras existe un proceso en ejecución.")
            return
        workspace = self._workspace_repo.get_workspace(workspace_id)
        if not messagebox.askyesno("Eliminar trabajo", f"Quitar '{workspace.name}' de la lista? Sus archivos se conservarán."):
            return
        delete_workspace_record(self._workspace_repo, workspace_id)
        if self._active_workspace_id == workspace_id:
            self._active_workspace_id = None; self._workspace_tracker = None; self._active_workspace_path = None
        self._workspace_selected_id = None
        self._reload_workspaces()
        self.workspace_status.set("Trabajo eliminado de la lista. Archivos conservados.")

    def _delete_selected_workspace_with_files(self):
        workspace_id = self._workspace_selected_id
        if not workspace_id or self._workspace_repo is None:
            messagebox.showinfo("Trabajos", "Selecciona un trabajo.")
            return
        if self._workspace_busy():
            messagebox.showwarning("Trabajos", "No se puede eliminar mientras existe un proceso en ejecución.")
            return
        workspace = self._workspace_repo.get_workspace(workspace_id)
        path = self._workspace_path_for(workspace_id)
        if not messagebox.askyesno("Eliminar trabajo y archivos", f"Esta acción elimina '{workspace.name}' y toda su carpeta de resultados. No se puede deshacer. ¿Continuar?"):
            return
        delete_workspace_files(path)
        delete_workspace_record(self._workspace_repo, workspace_id)
        if self._active_workspace_id == workspace_id:
            self._active_workspace_id = None; self._workspace_tracker = None; self._active_workspace_path = None
        self._workspace_selected_id = None
        self._reload_workspaces()
        self.workspace_status.set("Trabajo y archivos eliminados.")


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
