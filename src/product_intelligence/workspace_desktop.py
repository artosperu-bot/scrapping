from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .provider_desktop import App as ProviderApp
from .workspace_service import WorkspaceService
from .workspace_tracking import WorkspaceRunTracker
from .workspaces import Stage, WorkspaceRepository


WORKSPACE_NAV_KEY = "workspaces"


def default_workspace_db_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return root / "ProductIntelligence" / "workspaces.db"
    return Path.home() / ".product_intelligence" / "workspaces.db"


class App(ProviderApp):
    """Final additive shell for persistent jobs; existing engines remain inherited."""

    def __init__(self):
        self._workspace_repo: WorkspaceRepository | None = None
        self._workspace_service: WorkspaceService | None = None
        self._workspace_tracker: WorkspaceRunTracker | None = None
        self._workspace_selected_id: str | None = None
        self._active_workspace_id: str | None = None
        self._workspace_product_ids: dict[int, str] = {}
        self._workspace_core_active = False
        self._workspace_core_watching = False
        self._workspace_core_success: bool | None = None
        self._workspace_media_active = False
        self._workspace_media_error = False
        self._workspace_price_active = False
        super().__init__()
        self._workspace_repo = WorkspaceRepository(default_workspace_db_path())
        self._workspace_service = WorkspaceService(self._workspace_repo)
        self._workspace_service.recover_interrupted_runs()
        self._install_workspace_page()

    def destroy(self):
        repo = self._workspace_repo
        if repo is not None:
            try:
                repo.close()
            except Exception:
                pass
        super().destroy()

    def emit(self, msg):
        text = str(msg)
        super().emit(text)
        if self._workspace_core_watching:
            if text == "=== TERMINADO ===":
                self._workspace_core_success = True
            elif text.startswith("Traceback (most recent call last)"):
                self._workspace_core_success = False
        if self._workspace_media_active and text.startswith("Traceback (most recent call last)"):
            self._workspace_media_error = True

    def analyze_excel(self):
        return super().analyze_excel()

    def _apply_analysis_result(self, data: dict):
        super()._apply_analysis_result(data)
        self._refresh_shared_product_consumers()
        if self.preflight is not None and self._active_workspace_id:
            self._sync_workspace_products()
            self._reload_workspaces(select_id=self._active_workspace_id)

    def _shared_product_label(self, index: int, row: dict) -> str:
        identity = self._identity_for_index(index)
        if identity is not None:
            value = (
                identity.mpn
                or identity.ean
                or identity.upc
                or identity.gtin
                or identity.sku
                or identity.model
                or identity.product_name
            )
            if value:
                return str(value)
        return str(row.get("model") or row.get("product_name") or f"Producto {index + 1}")

    def _refresh_shared_product_consumers(self):
        """Refresh UI consumers only after async Excel analysis has committed product_rows."""
        rows = list(self.product_rows)

        media_list = getattr(self, "media_product_list", None)
        if media_list is not None:
            self.media_manual_urls = {i: list(self.manual_urls.get(i, [])) for i in range(len(rows))}
            self._media_current_index = None
            media_list.delete(0, "end")
            for index, row in enumerate(rows):
                media_list.insert("end", self._shared_product_label(index, row))
            if rows:
                media_list.selection_set(0)
                self._on_media_product_select()
                self.media_status.set(f"{len(rows)} productos listos para multimedia.")
            else:
                self.media_status.set("Analiza un Excel para cargar los productos.")
            self._clear_media_gallery()

        price_list = getattr(self, "price_product_list", None)
        if price_list is not None:
            price_list.delete(0, "end")
            for index, row in enumerate(rows):
                price_list.insert("end", self._shared_product_label(index, row))
            if rows:
                price_list.selection_set(0)
                self.price_status.set(f"{len(rows)} productos listos para comparar precios.")
            else:
                self.price_status.set("Analiza un Excel para cargar productos.")

    def run(self):
        if not self._active_workspace_id or self._workspace_tracker is None:
            return super().run()
        self._sync_workspace_products()
        product_ids = [self._workspace_product_ids[i] for i in sorted(self._workspace_product_ids)]
        self._workspace_core_success = None
        self._workspace_core_watching = True
        super().run()
        if not product_ids or not self.runbtn.instate(("disabled",)):
            self._workspace_core_watching = False
            return
        self._workspace_tracker.begin_core(product_ids)
        self._workspace_core_active = True
        self.after(200, self._monitor_core_run)

    def _monitor_core_run(self):
        if not self._workspace_core_active or self._workspace_tracker is None:
            return
        if self.runbtn.instate(("disabled",)):
            self.after(200, self._monitor_core_run)
            return
        success = self._workspace_core_success is True
        error = None if success else "Core pipeline ended without a successful terminal marker."
        self._workspace_tracker.finish_core(success=success, error=error)
        self._workspace_core_active = False
        self._workspace_core_watching = False
        self._reload_workspaces(select_id=self._active_workspace_id)

    def _start_media_indices(self, indices: list[int]):
        was_running = bool(getattr(self, "_media_running", False))
        super()._start_media_indices(indices)
        if was_running or not getattr(self, "_media_running", False) or self._workspace_tracker is None:
            return
        product_ids = [self._workspace_product_ids[i] for i in indices if i in self._workspace_product_ids]
        if not product_ids:
            return
        self._workspace_media_error = False
        self._workspace_tracker.begin_stage(product_ids, Stage.MULTIMEDIA)
        self._workspace_media_active = True
        self.after(200, self._monitor_media_run)

    def _monitor_media_run(self):
        if not self._workspace_media_active or self._workspace_tracker is None:
            return
        if getattr(self, "_media_running", False):
            self.after(200, self._monitor_media_run)
            return
        self._workspace_tracker.finish_stage(
            Stage.MULTIMEDIA,
            success=not self._workspace_media_error,
            error="Multimedia worker ended with a fatal error." if self._workspace_media_error else None,
        )
        self._workspace_media_active = False
        self._reload_workspaces(select_id=self._active_workspace_id)

    def _start_price_indices(self, indices):
        was_running = bool(getattr(self, "_price_running", False))
        super()._start_price_indices(indices)
        if was_running or not getattr(self, "_price_running", False) or self._workspace_tracker is None:
            return
        product_ids = [self._workspace_product_ids[i] for i in indices if i in self._workspace_product_ids]
        if not product_ids:
            return
        self._workspace_tracker.begin_stage(product_ids, Stage.PRICES)
        self._workspace_price_active = True
        self.after(200, self._monitor_price_run)

    def _monitor_price_run(self):
        if not self._workspace_price_active or self._workspace_tracker is None:
            return
        if getattr(self, "_price_running", False):
            self.after(200, self._monitor_price_run)
            return
        had_error = bool(getattr(self, "_price_had_error", False))
        self._workspace_tracker.finish_stage(
            Stage.PRICES,
            success=not had_error,
            error="Price Intelligence ended with an error." if had_error else None,
        )
        self._workspace_price_active = False
        self._reload_workspaces(select_id=self._active_workspace_id)

    def _sync_workspace_products(self):
        if not self._active_workspace_id or self._workspace_repo is None:
            return
        mapping: dict[int, str] = {}
        for index, row in enumerate(self.product_rows):
            identity = self._identity_for_index(index)
            if identity is None:
                continue
            primary = str(
                identity.mpn
                or identity.ean
                or identity.upc
                or identity.gtin
                or identity.sku
                or identity.model
                or identity.product_name
                or ""
            ).strip()
            if not primary:
                continue
            product = self._workspace_repo.find_product(self._active_workspace_id, primary)
            if product is None:
                product = self._workspace_repo.add_product(
                    self._active_workspace_id,
                    part_number=primary,
                    brand=identity.brand or row.get("brand"),
                    model=identity.model or row.get("model") or row.get("product_name"),
                )
            mapping[index] = product.id
        self._workspace_product_ids = mapping

    def _activate_workspace(self, workspace_id: str):
        if self._workspace_repo is None:
            return
        self._active_workspace_id = workspace_id
        self._workspace_selected_id = workspace_id
        self._workspace_tracker = WorkspaceRunTracker(self._workspace_repo, workspace_id)
        self._workspace_product_ids = {}

    def _show_workspace(self, key: str):
        super()._show_workspace(key)
        if key == WORKSPACE_NAV_KEY and hasattr(self, "_page_title"):
            self._page_title.set("Trabajos")
            self._page_subtitle.set("Crea, reabre y separa trabajos persistentes sin duplicar los motores de Product Intelligence.")
            self._reload_workspaces()

    def _install_workspace_page(self):
        self.workspaces_tab = ttk.Frame(self.notebook, style="Page.TFrame", padding=(12, 12))
        self.notebook.insert(1, self.workspaces_tab, text="Trabajos")
        self._workspace_tabs[WORKSPACE_NAV_KEY] = self.workspaces_tab

        nav_parent = self._nav_buttons["products"].master
        self._workspaces_nav_button = ttk.Button(
            nav_parent,
            text="▤   Trabajos",
            style="Nav.TButton",
            command=lambda: self._show_workspace(WORKSPACE_NAV_KEY),
        )
        self._workspaces_nav_button.pack(fill="x", padx=10, pady=(2, 2), before=self._nav_buttons["products"])
        self._nav_buttons[WORKSPACE_NAV_KEY] = self._workspaces_nav_button

        create_box = ttk.LabelFrame(self.workspaces_tab, text="Nuevo trabajo", style="Card.TLabelframe")
        create_box.pack(fill="x", pady=(0, 12))
        create_box.columnconfigure(1, weight=1)

        self.workspace_name = tk.StringVar()
        self.workspace_profile = tk.StringVar(value="legacy")
        self.workspace_status = tk.StringVar(value="Listo")

        ttk.Label(create_box, text="Nombre").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(create_box, textvariable=self.workspace_name).grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Label(create_box, text="Perfil Excel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(create_box, textvariable=self.workspace_profile, width=24).grid(row=1, column=1, sticky="w", pady=5)

        actions = ttk.Frame(create_box)
        actions.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))
        ttk.Button(actions, text="Crear trabajo", style="Primary.TButton", command=self._create_workspace).pack(side="left")
        ttk.Button(actions, text="Actualizar lista", command=self._reload_workspaces).pack(side="left", padx=(8, 0))

        info = ttk.Label(
            create_box,
            text="El trabajo guarda el Excel activo y su perfil. Scraping, PDFs, Multimedia y Precios siguen usando los motores actuales.",
            wraplength=920,
        )
        info.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

        list_box = ttk.LabelFrame(self.workspaces_tab, text="Trabajos guardados", style="Card.TLabelframe")
        list_box.pack(fill="both", expand=True)
        columns = ("name", "excel", "profile", "products", "status", "created")
        self.workspace_tree = ttk.Treeview(list_box, columns=columns, show="headings", style="Modern.Treeview")
        for column, title in (
            ("name", "Trabajo"),
            ("excel", "Excel"),
            ("profile", "Perfil"),
            ("products", "Productos"),
            ("status", "Estado"),
            ("created", "Creado"),
        ):
            self.workspace_tree.heading(column, text=title)
        self.workspace_tree.column("name", width=230, anchor="w")
        self.workspace_tree.column("excel", width=300, anchor="w")
        self.workspace_tree.column("profile", width=110, anchor="w")
        self.workspace_tree.column("products", width=80, anchor="center")
        self.workspace_tree.column("status", width=110, anchor="w")
        self.workspace_tree.column("created", width=160, anchor="w")
        self.workspace_tree.pack(fill="both", expand=True)
        self.workspace_tree.bind("<<TreeviewSelect>>", self._on_workspace_selected)

        bottom = ttk.Frame(self.workspaces_tab, style="Page.TFrame")
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Label(bottom, textvariable=self.workspace_status).pack(side="left")
        ttk.Button(bottom, text="Abrir / reanudar", style="Primary.TButton", command=self._open_selected_workspace).pack(side="right")

        self._reload_workspaces()

    def _create_workspace(self):
        if self._workspace_repo is None:
            return
        name = self.workspace_name.get().strip()
        if not name:
            messagebox.showinfo("Trabajos", "Ingresa un nombre para el trabajo.")
            return
        excel_path = str(self.excel.get() or "").strip() if hasattr(self, "excel") else ""
        profile = self.workspace_profile.get().strip() or "legacy"
        workspace = self._workspace_repo.create_workspace(
            name,
            excel_path=excel_path or None,
            template_profile_id=profile,
        )
        self.workspace_name.set("")
        self._activate_workspace(workspace.id)
        if self.preflight is not None:
            self._sync_workspace_products()
        self.workspace_status.set(f"Trabajo activo: {workspace.name}")
        self._reload_workspaces(select_id=workspace.id)

    def _workspace_state_label(self, workspace_id: str) -> str:
        if self._workspace_repo is None:
            return "Pendiente"
        products = self._workspace_repo.list_products(workspace_id)
        if not products:
            return "Pendiente"
        runs = [self._workspace_repo.latest_run(product.id) for product in products]
        statuses = [run.status.value for run in runs if run is not None]
        if "ERROR" in statuses:
            return "Error"
        if "RUNNING" in statuses:
            return "En curso"
        if statuses and len(statuses) == len(products) and all(status == "COMPLETED" for status in statuses):
            return "Completado"
        if any(status == "PAUSED" for status in statuses):
            return "Pausado"
        return "Pendiente"

    def _reload_workspaces(self, select_id: str | None = None):
        tree = getattr(self, "workspace_tree", None)
        if tree is None or self._workspace_repo is None:
            return
        for item in tree.get_children():
            tree.delete(item)
        target = select_id or self._workspace_selected_id
        for workspace in self._workspace_repo.list_workspaces():
            excel_name = Path(workspace.excel_path).name if workspace.excel_path else "Sin Excel"
            products = self._workspace_repo.list_products(workspace.id)
            tree.insert(
                "",
                "end",
                iid=workspace.id,
                values=(
                    workspace.name,
                    excel_name,
                    workspace.template_profile_id or "legacy",
                    len(products),
                    self._workspace_state_label(workspace.id),
                    workspace.created_at[:19],
                ),
            )
        if target and tree.exists(target):
            tree.selection_set(target)
            tree.focus(target)

    def _on_workspace_selected(self, _event=None):
        selection = self.workspace_tree.selection()
        self._workspace_selected_id = selection[0] if selection else None
        if self._workspace_selected_id and self._workspace_repo is not None:
            workspace = self._workspace_repo.get_workspace(self._workspace_selected_id)
            self.workspace_status.set(f"Seleccionado: {workspace.name}")

    def _open_selected_workspace(self):
        if not self._workspace_selected_id or self._workspace_repo is None:
            messagebox.showinfo("Trabajos", "Selecciona un trabajo guardado.")
            return
        workspace = self._workspace_repo.get_workspace(self._workspace_selected_id)
        self._activate_workspace(workspace.id)
        if workspace.excel_path and hasattr(self, "excel"):
            self.excel.set(workspace.excel_path)
            if Path(workspace.excel_path).exists():
                self.analyze_excel()
        if hasattr(self, "global_status"):
            self.global_status.set(f"Trabajo activo: {workspace.name}")
        self.workspace_status.set(f"Trabajo abierto: {workspace.name}")
        self._show_workspace("dashboard")


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
