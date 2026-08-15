from __future__ import annotations

from tkinter import ttk

from .organized_desktop import App as OrganizedApp
from .workspace_desktop import App as WorkspaceApp


class App(OrganizedApp):
    """Final shell with deterministic workspace-management button placement."""

    def _install_workspace_page(self):
        # Build the validated persistent workspace page directly, then append the
        # new management bar. This avoids depending on sibling pack ordering.
        WorkspaceApp._install_workspace_page(self)
        management = ttk.Frame(self.workspaces_tab, style="Page.TFrame")
        management.pack(fill="x", pady=(8, 0))
        ttk.Button(management, text="Abrir carpeta", command=self._open_workspace_folder).pack(side="left")
        ttk.Button(management, text="Limpiar resultados", command=self._clean_selected_workspace).pack(side="left", padx=(8, 0))
        ttk.Button(management, text="Eliminar trabajo", command=self._delete_selected_workspace).pack(side="left", padx=(8, 0))
        ttk.Button(management, text="Eliminar trabajo y archivos...", command=self._delete_selected_workspace_with_files).pack(side="left", padx=(8, 0))


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
