from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from .mercadolibre_oauth import (
    MercadoLibreApiClient,
    MercadoLibreAuthError,
    MercadoLibreAuthService,
    MercadoLibreTokenStore,
)


class MercadoLibreDesktopMixin:
    """Add one-time Mercado Libre OAuth setup to the existing Configuración page."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.after(600, self._start_ml_startup_validation)

    def _install_settings_workspace(self):
        super()._install_settings_workspace()
        self._install_mercadolibre_settings_box()

    def _install_mercadolibre_settings_box(self):
        store = MercadoLibreTokenStore()
        current = store.load()

        self.ml_client_id_input = tk.StringVar(value=current.client_id if current else "")
        self.ml_client_secret_input = tk.StringVar()
        self.ml_refresh_token_input = tk.StringVar()
        self.ml_access_token_input = tk.StringVar()
        self.ml_status = tk.StringVar(value=self._ml_state_text(current))
        self.ml_details = tk.StringVar(value=self._ml_details_text(current))

        box = ttk.LabelFrame(self.settings_tab, text="Mercado Libre API", style="Card.TLabelframe")
        box.pack(fill="x", pady=(0, 12))

        ttk.Label(
            box,
            text=(
                "Configura estas credenciales una sola vez. Luego Product Intelligence valida expires_at y "
                "renueva access/refresh tokens automáticamente al abrir y antes de usar Mercado Libre."
            ),
            wraplength=920,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        ttk.Label(box, text="Client ID / App ID").grid(row=1, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.ml_client_id_input, width=42).grid(row=1, column=1, sticky="ew", padx=(10, 18))
        ttk.Label(box, text="Client Secret").grid(row=1, column=2, sticky="w")
        ttk.Entry(box, textvariable=self.ml_client_secret_input, show="•", width=42).grid(row=1, column=3, sticky="ew", padx=(10, 0))

        ttk.Label(box, text="Refresh Token").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(box, textvariable=self.ml_refresh_token_input, show="•", width=42).grid(row=2, column=1, sticky="ew", padx=(10, 18), pady=(8, 0))
        ttk.Label(box, text="Access Token (opcional)").grid(row=2, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(box, textvariable=self.ml_access_token_input, show="•", width=42).grid(row=2, column=3, sticky="ew", padx=(10, 0), pady=(8, 0))

        status_row = ttk.Frame(box)
        status_row.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Label(status_row, textvariable=self.ml_status).pack(side="left")
        ttk.Label(status_row, textvariable=self.ml_details).pack(side="left", padx=(16, 0))

        actions = ttk.Frame(box)
        actions.grid(row=4, column=0, columnspan=4, sticky="e", pady=(10, 0))
        self.ml_save_button = ttk.Button(actions, text="Guardar configuración", style="Primary.TButton", command=self._save_ml_configuration)
        self.ml_save_button.pack(side="left")
        self.ml_test_button = ttk.Button(actions, text="Probar conexión", command=self._test_ml_connection)
        self.ml_test_button.pack(side="left", padx=(8, 0))
        self.ml_refresh_button = ttk.Button(actions, text="Renovar token ahora", command=self._force_ml_refresh)
        self.ml_refresh_button.pack(side="left", padx=(8, 0))

        box.columnconfigure(1, weight=1)
        box.columnconfigure(3, weight=1)

    @staticmethod
    def _ml_state_text(state) -> str:
        if state is None or not state.client_id or not state.client_secret or not state.refresh_token:
            return "SIN CONFIGURAR"
        return "CONFIGURADO · renovación automática activa"

    @staticmethod
    def _ml_details_text(state) -> str:
        if state is None:
            return ""
        pieces = []
        if state.expires_at:
            try:
                expiry = datetime.fromisoformat(state.expires_at.replace("Z", "+00:00"))
                pieces.append(f"Expira: {expiry.astimezone().strftime('%Y-%m-%d %H:%M')}")
            except ValueError:
                pieces.append("Expiración: pendiente")
        if state.user_id is not None:
            pieces.append(f"User ID: {state.user_id}")
        if state.site_id:
            pieces.append(f"Site: {state.site_id}")
        return " · ".join(pieces)

    def _set_ml_buttons(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for name in ("ml_save_button", "ml_test_button", "ml_refresh_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=state)

    def _save_ml_configuration(self):
        client_id = self.ml_client_id_input.get().strip()
        client_secret = self.ml_client_secret_input.get().strip()
        refresh_token = self.ml_refresh_token_input.get().strip()
        access_token = self.ml_access_token_input.get().strip()
        if not client_id or not client_secret or not refresh_token:
            messagebox.showinfo(
                "Mercado Libre API",
                "Ingresa Client ID / App ID, Client Secret y Refresh Token inicial.",
            )
            return
        self.ml_status.set("CONFIGURANDO Y VALIDANDO…")
        self._set_ml_buttons(False)

        def work():
            try:
                auth = MercadoLibreAuthService()
                result = auth.configure(
                    client_id=client_id,
                    client_secret=client_secret,
                    refresh_token=refresh_token,
                    access_token=access_token,
                )
                error = None
            except Exception as exc:
                result = None
                error = exc
            self.after(0, lambda: self._finish_ml_action(result, error, "Configuración guardada y token validado."))

        threading.Thread(target=work, daemon=True, name="ml-oauth-configure").start()

    def _test_ml_connection(self):
        self.ml_status.set("PROBANDO CONEXIÓN…")
        self._set_ml_buttons(False)

        def work():
            try:
                client = MercadoLibreApiClient()
                profile = client.users_me()
                result = client.auth.current_state()
                message = f"Conexión correcta. User ID: {profile.get('id', '-')} · Site: {profile.get('site_id', '-')}"
                error = None
            except Exception as exc:
                result = None
                message = ""
                error = exc
            self.after(0, lambda: self._finish_ml_action(result, error, message, show_success=True))

        threading.Thread(target=work, daemon=True, name="ml-oauth-test").start()

    def _force_ml_refresh(self):
        self.ml_status.set("RENOVANDO TOKEN…")
        self._set_ml_buttons(False)

        def work():
            try:
                auth = MercadoLibreAuthService()
                auth.force_refresh()
                result = auth.current_state()
                error = None
            except Exception as exc:
                result = None
                error = exc
            self.after(0, lambda: self._finish_ml_action(result, error, "Token renovado y persistido.", show_success=True))

        threading.Thread(target=work, daemon=True, name="ml-oauth-refresh").start()

    def _start_ml_startup_validation(self):
        auth = MercadoLibreAuthService()
        if not auth.is_configured():
            return
        self.ml_status.set("VALIDANDO SESIÓN…")

        def work():
            try:
                auth.get_valid_access_token()
                result = auth.current_state()
                error = None
            except Exception as exc:
                result = auth.current_state()
                error = exc
            self.after(0, lambda: self._finish_ml_startup(result, error))

        threading.Thread(target=work, daemon=True, name="ml-oauth-startup").start()

    def _finish_ml_startup(self, state, error):
        if error is None:
            self.ml_status.set(self._ml_state_text(state))
            self.ml_details.set(self._ml_details_text(state))
            return
        self.ml_status.set(self._ml_error_text(error))
        self.ml_details.set(self._ml_details_text(state))

    def _finish_ml_action(self, state, error, success_message: str, show_success: bool = False):
        self._set_ml_buttons(True)
        if error is not None:
            self.ml_status.set(self._ml_error_text(error))
            current = MercadoLibreTokenStore().load()
            self.ml_details.set(self._ml_details_text(current))
            messagebox.showerror("Mercado Libre API", self._ml_error_text(error))
            return
        self.ml_client_secret_input.set("")
        self.ml_refresh_token_input.set("")
        self.ml_access_token_input.set("")
        self.ml_status.set(self._ml_state_text(state))
        self.ml_details.set(self._ml_details_text(state))
        if show_success:
            messagebox.showinfo("Mercado Libre API", success_message)

    @staticmethod
    def _ml_error_text(error: Exception) -> str:
        if isinstance(error, MercadoLibreAuthError):
            messages = {
                "ML_AUTH_NOT_CONFIGURED": "Mercado Libre no está configurado.",
                "ML_REFRESH_TOKEN_INVALID": "El Refresh Token fue rechazado o ya no es válido.",
                "ML_CLIENT_CREDENTIALS_INVALID": "Client ID / Client Secret rechazados.",
                "ML_AUTH_NETWORK_ERROR": "No se pudo conectar con Mercado Libre. La configuración anterior no fue eliminada.",
                "ERROR_AUTH_MERCADOLIBRE": "Mercado Libre rechazó la sesión incluso después de renovarla.",
            }
            return messages.get(error.code, f"Error de autenticación Mercado Libre: {error.code}")
        return f"Error Mercado Libre: {type(error).__name__}"
