from __future__ import annotations

import queue
import re
import tkinter as tk
from tkinter import ttk

from .media_desktop import App as MediaApp
from .media_progress import BatchProgress
from .progress_animation import ProgressAnimation


class _MirrorQueue(queue.Queue):
    def __init__(self, mirror: queue.Queue):
        super().__init__()
        self._mirror = mirror

    def put(self, item, block=True, timeout=None):
        self._mirror.put(item)
        return super().put(item, block=block, timeout=timeout)


class App(MediaApp):
    """Adds truthful progress visualization without changing the media engine."""

    def __init__(self):
        self._progress_events: queue.Queue = queue.Queue()
        self._progress = BatchProgress(total=0)
        self._progress_had_error = False
        super().__init__()
        self.media_events = _MirrorQueue(self._progress_events)
        self.after(150, self._drain_progress_events)

    def _build_media_tab(self):
        super()._build_media_tab()
        self.media_gallery_box = self.media_canvas.master
        self.media_gallery_box.pack_forget()

        progress_box = ttk.LabelFrame(self.media_tab, text="Progreso del proceso", padding=8, height=165)
        progress_box.pack_propagate(False)
        progress_box.pack(fill="x", pady=(8, 0))

        left = ttk.Frame(progress_box)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(progress_box)
        right.pack(side="right", padx=(12, 0))

        self.media_progress_title = tk.StringVar(value="Listo para buscar multimedia")
        ttk.Label(left, textvariable=self.media_progress_title, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        row1 = ttk.Frame(left)
        row1.pack(fill="x", pady=(6, 2))
        ttk.Label(row1, text="Producto actual", width=15).pack(side="left")
        self.media_product_progress = ttk.Progressbar(row1, maximum=100, mode="determinate")
        self.media_product_progress.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self.media_product_percent = tk.StringVar(value="0%")
        ttk.Label(row1, textvariable=self.media_product_percent, width=9).pack(side="left")

        row2 = ttk.Frame(left)
        row2.pack(fill="x", pady=(2, 2))
        ttk.Label(row2, text="Progreso general", width=15).pack(side="left")
        self.media_overall_progress = ttk.Progressbar(row2, maximum=100, mode="determinate")
        self.media_overall_progress.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self.media_overall_percent = tk.StringVar(value="0%")
        ttk.Label(row2, textvariable=self.media_overall_percent, width=9).pack(side="left")

        self.media_progress_detail = tk.StringVar(value="0 productos completados")
        ttk.Label(left, textvariable=self.media_progress_detail).pack(anchor="w", pady=(4, 0))

        self.media_progress_animation = ProgressAnimation(right, width=180, height=105)
        self.media_progress_animation.pack(anchor="center")
        self.media_gallery_box.pack(fill="both", expand=True)

    def _start_media_indices(self, indices: list[int]):
        valid_count = sum(1 for index in indices if self._identity_for_index(index) is not None)
        self._progress = BatchProgress(total=valid_count)
        self._progress_had_error = False
        self._set_progress_ui()
        if valid_count:
            self.media_progress_animation.set_running("Procesando multimedia…")
        return super()._start_media_indices(indices)

    def _drain_progress_events(self):
        try:
            while True:
                event = self._progress_events.get_nowait()
                self._apply_progress_event(event)
        except queue.Empty:
            pass
        self.after(150, self._drain_progress_events)

    def _set_media_running(self, text: str):
        if self.media_product_progress.cget("mode") != "indeterminate":
            self.media_product_progress.stop()
            self.media_product_progress.configure(mode="indeterminate")
            self.media_product_progress.start(12)
        self.media_product_percent.set("En curso")
        self.media_progress_animation.set_running(text)

    def _apply_progress_event(self, event: dict):
        event_type = str(event.get("type") or "")
        if event_type == "batch_status":
            message = str(event.get("message") or "")
            match = re.match(r"(\d+)/(\d+)\s+—\s+(.+)", message)
            if match:
                position = max(0, int(match.group(1)) - 1)
                self._progress.start_product(position, match.group(3))
                self._set_media_running(f"Procesando producto {match.group(1)} de {match.group(2)}")
            else:
                self._set_media_running(message or "Procesando multimedia…")
        elif event_type == "status":
            self._set_media_running(str(event.get("message") or "Buscando fuentes…"))
        elif event_type == "page":
            status = str(event.get("status") or "")
            text = "Buscando fuentes…" if status == "fetching" else "Validando producto…"
            if status == "validated":
                text = "Analizando multimedia…"
            self._set_media_running(text)
        elif event_type == "media":
            self._set_media_running("Guardando multimedia…")
        elif event_type == "media_rejected":
            self._set_media_running("Validando multimedia…")
        elif event_type == "done":
            self._progress.finish_product(
                downloaded=int(event.get("downloaded") or 0),
                metadata_only=int(event.get("metadata_only") or 0),
            )
            self.media_product_progress.stop()
            self.media_product_progress.configure(mode="determinate", value=100)
            self.media_product_percent.set("100%")
            if self._progress.completed < self._progress.total:
                self.media_progress_animation.set_running("Finalizando producto…")
        elif event_type == "fatal":
            self._progress_had_error = True
            self._progress.finish_product(error=True)
            self.media_product_progress.stop()
            self.media_product_progress.configure(mode="determinate")
            error = str(event.get("error") or "Error durante multimedia")
            self.media_progress_title.set(error)
            self.media_progress_animation.set_error(error)
        elif event_type == "batch_done":
            self.media_product_progress.stop()
            if not self._progress_had_error and self._progress.total and self._progress.completed >= self._progress.total:
                self.media_product_progress.configure(mode="determinate", value=100)
                self.media_product_percent.set("100%")
                self.media_overall_progress["value"] = 100
                self.media_overall_percent.set("100%")
                self.media_progress_title.set("Proceso completado")
                self.media_progress_animation.set_completed("Proceso completado")
            elif self._progress_had_error:
                self.media_progress_animation.set_error(self.media_progress_title.get())
        self._set_progress_ui()

    def _set_progress_ui(self):
        if not hasattr(self, "media_overall_progress"):
            return
        total = max(0, self._progress.total)
        completed = max(0, min(total, self._progress.completed))
        overall = int((completed / total) * 100) if total else 0
        if not (completed >= total and total and not self._progress_had_error):
            overall = min(overall, 99)
        self.media_overall_progress["value"] = overall
        self.media_overall_percent.set(f"{overall}%")
        if self._progress.current_label and not self._progress_had_error:
            self.media_progress_title.set(self._progress.current_label)
        self.media_progress_detail.set(
            f"{completed}/{total} productos completados  ·  "
            f"{self._progress.downloaded} archivos descargados  ·  "
            f"{self._progress.metadata_only} enlaces externos  ·  {self._progress.errors} errores"
        )


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
