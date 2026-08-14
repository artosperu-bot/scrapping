from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .key_store import delete_value, load_value, save_value
from .pdf_desktop import App as PdfApp
from .provider_settings import ProviderSettings


_PROVIDER_KEYS = {
    "ocr": "ocr_space_api_key",
    "mistral": "mistral_api_key",
}


def credential_state(name: str) -> str:
    return "GUARDADA · prueba real pendiente" if load_value(_PROVIDER_KEYS[name]) else "SIN CONFIGURAR"


class App(PdfApp):
    """Final desktop shell with one provider configuration workspace."""

    def __init__(self):
        super().__init__()
        self._provider_settings = ProviderSettings()
        self._install_settings_workspace()

    def _show_workspace(self, key: str):
        super()._show_workspace(key)
        if key == "settings" and hasattr(self, "_page_title"):
            self._page_title.set("Configuración")
            self._page_subtitle.set("Configura proveedores opcionales sin exponer credenciales ni alterar ejecuciones en curso.")

    def _install_settings_workspace(self):
        self.settings_tab = ttk.Frame(self.notebook, style="Page.TFrame", padding=(12, 12))
        self.notebook.add(self.settings_tab, text="Configuración")
        self._workspace_tabs["settings"] = self.settings_tab

        self._settings_nav_button = ttk.Button(
            self.sidebar,
            text="⚙   Configuración",
            style="Nav.TButton",
            command=lambda: self._show_workspace("settings"),
        )
        self._settings_nav_button.pack(fill="x", padx=10, pady=(10, 2))
        self._nav_buttons["settings"] = self._settings_nav_button

        intro = ttk.LabelFrame(self.settings_tab, text="Proveedores opcionales", style="Card.TLabelframe")
        intro.pack(fill="x", pady=(0, 12))
        ttk.Label(
            intro,
            text="Las credenciales se guardan en el almacén seguro del sistema. No se escriben en settings.json, logs, auditoría ni Excel.",
            wraplength=920,
        ).pack(anchor="w")
        ttk.Label(
            intro,
            text="Las pruebas reales de conexión están deshabilitadas en esta fase.",
        ).pack(anchor="w", pady=(4, 0))

        values = self._provider_settings.as_dict()
        self.ocr_enabled = tk.BooleanVar(value=bool(values.get("ocr_space_enabled", True)))
        self.mistral_enabled = tk.BooleanVar(value=bool(values.get("mistral_enabled", True)))
        self.mistral_model = tk.StringVar(value=str(values.get("mistral_model") or "mistral-small-latest"))
        self.request_timeout = tk.IntVar(value=int(values.get("request_timeout") or 20))
        self.ocr_key_input = tk.StringVar()
        self.mistral_key_input = tk.StringVar()
        self.ocr_status = tk.StringVar(value=credential_state("ocr"))
        self.mistral_status = tk.StringVar(value=credential_state("mistral"))

        self._provider_box(
            title="OCR.space",
            enabled=self.ocr_enabled,
            key_var=self.ocr_key_input,
            status_var=self.ocr_status,
            provider="ocr",
        ).pack(fill="x", pady=(0, 12))
        self._provider_box(
            title="Mistral",
            enabled=self.mistral_enabled,
            key_var=self.mistral_key_input,
            status_var=self.mistral_status,
            provider="mistral",
            model_var=self.mistral_model,
        ).pack(fill="x", pady=(0, 12))

        general = ttk.LabelFrame(self.settings_tab, text="Ejecución", style="Card.TLabelframe")
        general.pack(fill="x")
        row = ttk.Frame(general)
        row.pack(fill="x")
        ttk.Label(row, text="Timeout de proveedor (segundos)").pack(side="left")
        ttk.Spinbox(row, from_=5, to=120, textvariable=self.request_timeout, width=8).pack(side="left", padx=10)
        ttk.Button(row, text="Guardar ajustes", style="Primary.TButton", command=self._save_non_secret_settings).pack(side="right")

    def _provider_box(self, *, title, enabled, key_var, status_var, provider, model_var=None):
        box = ttk.LabelFrame(self.settings_tab, text=title, style="Card.TLabelframe")
        ttk.Checkbutton(box, text="Habilitado", variable=enabled).grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(box, textvariable=status_var).grid(row=0, column=1, sticky="w", padx=(14, 0), pady=(0, 8))
        ttk.Label(box, text="API key").grid(row=1, column=0, sticky="w")
        entry = ttk.Entry(box, textvariable=key_var, show="•", width=54)
        entry.grid(row=1, column=1, sticky="ew", padx=(14, 8))
        box.columnconfigure(1, weight=1)
        actions = ttk.Frame(box)
        actions.grid(row=1, column=2, sticky="e")
        ttk.Button(actions, text="Guardar / reemplazar", command=lambda: self._save_key(provider, key_var, status_var)).pack(side="left")
        ttk.Button(actions, text="Borrar", command=lambda: self._delete_key(provider, key_var, status_var)).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Probar conexión · pendiente", state="disabled").pack(side="left", padx=(6, 0))
        if model_var is not None:
            ttk.Label(box, text="Modelo").grid(row=2, column=0, sticky="w", pady=(8, 0))
            ttk.Entry(box, textvariable=model_var, state="readonly", width=34).grid(row=2, column=1, sticky="w", padx=(14, 8), pady=(8, 0))
        return box

    def _save_key(self, provider: str, key_var: tk.StringVar, status_var: tk.StringVar):
        value = key_var.get().strip()
        if not value:
            messagebox.showinfo("Credencial", "Ingresa una clave para guardarla o reemplazarla.")
            return
        save_value(_PROVIDER_KEYS[provider], value)
        key_var.set("")
        status_var.set("GUARDADA · prueba real pendiente")

    def _delete_key(self, provider: str, key_var: tk.StringVar, status_var: tk.StringVar):
        delete_value(_PROVIDER_KEYS[provider])
        key_var.set("")
        status_var.set("SIN CONFIGURAR")

    def _save_non_secret_settings(self):
        self._provider_settings.set("ocr_space_enabled", bool(self.ocr_enabled.get()))
        self._provider_settings.set("mistral_enabled", bool(self.mistral_enabled.get()))
        self._provider_settings.set("mistral_model", "mistral-small-latest")
        self._provider_settings.set("request_timeout", max(5, min(120, int(self.request_timeout.get()))))
        self._provider_settings.save()
        self.mistral_model.set("mistral-small-latest")
        messagebox.showinfo("Configuración", "Ajustes no secretos guardados.")


def main():
    App().mainloop()
