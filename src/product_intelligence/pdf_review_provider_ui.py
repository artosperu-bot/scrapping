from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class PdfReviewProviderVisibilityMixin:
    """Show the real post-selection provider path inside Revisión PDF.

    This layer is UI-only. Credentials remain owned by ProviderApp/keyring and the
    existing reviewed-PDF allow-list remains the only path into document processing.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._install_pdf_review_provider_status()

    def _install_pdf_review_provider_status(self):
        tab = getattr(self, "pdf_review_tab", None)
        if tab is None:
            return
        self.pdf_review_provider_status = tk.StringVar()
        box = ttk.LabelFrame(
            tab,
            text="Procesamiento después de confirmar",
            style="Card.TLabelframe",
            padding=8,
        )
        box.pack(fill="x", pady=(0, 10), before=tab.winfo_children()[2] if len(tab.winfo_children()) > 2 else None)
        ttk.Label(
            box,
            textvariable=self.pdf_review_provider_status,
            wraplength=1120,
            justify="left",
        ).pack(anchor="w")
        self._pdf_review_refresh_provider_status()

    def _pdf_review_refresh_provider_status(self):
        target = getattr(self, "pdf_review_provider_status", None)
        if target is None:
            return

        ocr_enabled_var = getattr(self, "ocr_enabled", None)
        mistral_enabled_var = getattr(self, "mistral_enabled", None)
        ocr_state_var = getattr(self, "ocr_status", None)
        mistral_state_var = getattr(self, "mistral_status", None)

        ocr_enabled = bool(ocr_enabled_var.get()) if ocr_enabled_var is not None else False
        mistral_enabled = bool(mistral_enabled_var.get()) if mistral_enabled_var is not None else False
        ocr_state = str(ocr_state_var.get()) if ocr_state_var is not None else "SIN CONFIGURAR"
        mistral_state = str(mistral_state_var.get()) if mistral_state_var is not None else "SIN CONFIGURAR"

        ocr_label = "habilitado" if ocr_enabled else "deshabilitado"
        mistral_label = "habilitado" if mistral_enabled else "deshabilitado"
        target.set(
            f"OCR.space: {ocr_label} · {ocr_state}. Se usa solo si falta texto nativo suficiente en un PDF seleccionado. "
            f"Mistral: {mistral_label} · {mistral_state}. Se usa después, para generar la descripción desde hechos ya "
            "validados; no lee ni valida el PDF. La búsqueda, descarga, preview y selección no consumen OCR ni Mistral."
        )

    def _show_workspace(self, key: str):
        result = super()._show_workspace(key)
        if key == "pdf_review":
            self._pdf_review_refresh_provider_status()
        return result

    def _pdf_review_confirm(self):
        result = super()._pdf_review_confirm()
        self._pdf_review_refresh_provider_status()
        return result
