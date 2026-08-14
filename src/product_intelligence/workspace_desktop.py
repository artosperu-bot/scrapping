from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .provider_desktop import App as ProviderApp
from .workspace_service import WorkspaceService
from .workspaces import WorkspaceRepository


WORKSPACE_NAV_KEY = "workspaces"


def default_workspace_db_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return root / "ProductIntelligence" / "workspaces.db"
    return Path.home() / ".product_intelligence" / "workspaces.db"


class App(ProviderApp):
    """Final additive shell for persistent jobs; existing engines remain inherited."""

    def __init__(self):
        super().__init__()
        self._workspace_repo = WorkspaceRepository(default_workspace_db_path())
        self._workspace_service = WorkspaceService(self._workspace_repo)
        self._workspace_service.recover_interrupted_runs()
        self._workspace_selected_id: str | None = None
        self._install_workspace_page()

    def destroy(self):
        repo = getattr(self, "_workspace_repo", None)
        if repo is not None:
            try:
                repo.close()
            except Exception:
                pass
        super().destroy()

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

        self._workspaces_nav_button = ttk.Button(
            self.sidebar,
            text="▤   Trabajos",
            style="Nav.TButton",
            command=lambda: self._show_workspace(WORKSPACE_NAV_KEY),
        )
        self._workspaces_nav_button.pack(fill="x", padx=10, pady=(2, 2), before=self._nav_buttons.get("products"))
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
        columns = ("name", "excel", "profile", "created")
        self.workspace_tree = ttk.Treeview(list_box, columns=columns, show="headings", style="Modern.Treeview")
        self.workspace_tree.heading("name", text="Trabajo")
        self.workspace_tree.heading("excel", text="Excel")
        self.workspace_tree.heading("profile", text="Perfil")
        self.workspace_tree.heading("created", text="Creado")
        self.workspace_tree.column("name", width=260, anchor="w")
        self.workspace_tree.column("excel", width=360, anchor="w")
        self.workspace_tree.column("profile", width=140, anchor="w")
        self.workspace_tree.column("created", width=180, anchor="w")
        self.workspace_tree.pack(fill="both", expand=True)
        self.workspace_tree.bind("<<TreeviewSelect>>", self._on_workspace_selected)

        bottom = ttk.Frame(self.workspaces_tab, style="Page.TFrame")
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Label(bottom, textvariable=self.workspace_status).pack(side="left")
        ttk.Button(bottom, text="Abrir trabajo", style="Primary.TButton", command=self._open_selected_workspace).pack(side="right")

        self._reload_workspaces()

    def _create_workspace(self):
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
        self._workspace_selected_id = workspace.id
        self.workspace_status.set(f"Trabajo creado: {workspace.name}")
        self._reload_workspaces(select_id=workspace.id)

    def _reload_workspaces(self, select_id: str | None = None):
        tree = getattr(self, "workspace_tree", None)
        if tree is None:
            return
        for item in tree.get_children():
            tree.delete(item)
        target = select_id or self._workspace_selected_id
        for workspace in self._workspace_repo.list_workspaces():
            excel_name = Path(workspace.excel_path).name if workspace.excel_path else "Sin Excel"
            tree.insert(
                "",
                "end",
                iid=workspace.id,
                values=(workspace.name, excel_name, workspace.template_profile_id or "legacy", workspace.created_at[:19]),
            )
        if target and tree.exists(target):
            tree.selection_set(target)
            tree.focus(target)

    def _on_workspace_selected(self, _event=None):
        selection = self.workspace_tree.selection()
        self._workspace_selected_id = selection[0] if selection else None
        if self._workspace_selected_id:
            workspace = self._workspace_repo.get_workspace(self._workspace_selected_id)
            self.workspace_status.set(f"Seleccionado: {workspace.name}")

    def _open_selected_workspace(self):
        if not self._workspace_selected_id:
            messagebox.showinfo("Trabajos", "Selecciona un trabajo guardado.")
            return
        workspace = self._workspace_repo.get_workspace(self._workspace_selected_id)
        if workspace.excel_path and hasattr(self, "excel"):
            self.excel.set(workspace.excel_path)
        if hasattr(self, "global_status"):
            self.global_status.set(f"Trabajo activo: {workspace.name}")
        self.workspace_status.set(f"Trabajo abierto: {workspace.name}")
        self._show_workspace("dashboard")


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
