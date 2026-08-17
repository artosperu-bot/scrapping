from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class SocialVideoVisibilityMixin:
    """Restore the generic URL video downloader after the organized media rebuild."""

    def _build_media_tab(self):
        super()._build_media_tab()
        views = getattr(self, "media_views", None)
        if views is None:
            return
        tabs = list(views.tabs())
        if not tabs:
            return
        try:
            search_tab = views.nametowidget(tabs[0])
        except Exception:
            return

        # Snapshot existing packed siblings before creating the new widget so it can
        # never become its own `pack(before=...)` target.
        children = list(search_tab.winfo_children())
        before_target = children[-1] if children else None
        social_box = ttk.LabelFrame(search_tab, text="Descargar video por URL", padding=8)
        pack_kwargs = {"fill": "x", "pady": (7, 0)}
        if before_target is not None:
            pack_kwargs["before"] = before_target
        social_box.pack(**pack_kwargs)

        ttk.Label(
            social_box,
            text=(
                "Pega una URL pública de un sitio compatible con el motor de descarga. "
                "Se descarga un solo video y se normaliza a MP4; contenido privado, "
                "con login, DRM o no soportado se rechaza con un error explícito."
            ),
            wraplength=1040,
            justify="left",
        ).pack(anchor="w")

        row = ttk.Frame(social_box)
        row.pack(fill="x", pady=(5, 3))
        self.social_video_url = tk.StringVar()
        ttk.Entry(row, textvariable=self.social_video_url).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.social_video_quality = tk.StringVar(value="Mejor calidad")
        ttk.Combobox(
            row,
            textvariable=self.social_video_quality,
            values=("Mejor calidad", "1080p", "720p", "480p"),
            width=15,
            state="readonly",
        ).pack(side="left", padx=(0, 8))
        self.social_video_btn = ttk.Button(row, text="Descargar MP4", command=self._start_social_video_download)
        self.social_video_btn.pack(side="left")
        self.social_video_status = tk.StringVar(value="Listo para descargar un video por URL.")
        ttk.Label(social_box, textvariable=self.social_video_status, font=("Segoe UI", 9, "italic")).pack(anchor="w")
