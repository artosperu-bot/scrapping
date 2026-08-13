from __future__ import annotations

import math
import queue
import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageSequence, ImageTk

from .media_desktop import App as MediaApp
from .media_progress import BatchProgress


class _MirrorQueue(queue.Queue):
    def __init__(self, mirror: queue.Queue):
        super().__init__()
        self._mirror = mirror

    def put(self, item, block=True, timeout=None):
        self._mirror.put(item)
        return super().put(item, block=block, timeout=timeout)


class App(MediaApp):
    """Adds truthful progress visualization without changing the scraping engine."""

    def __init__(self):
        self._progress_events: queue.Queue = queue.Queue()
        self._progress = BatchProgress(total=0)
        self._wolf_frame = 0
        self._wolf_state = "idle"
        self._wolf_gif_frames: list[ImageTk.PhotoImage] = []
        self._wolf_gif_index = 0
        super().__init__()
        self._load_wolf_gif()
        self.media_events = _MirrorQueue(self._progress_events)
        self.after(150, self._drain_progress_events)
        self.after(160, self._animate_wolf)

    def _build_media_tab(self):
        super()._build_media_tab()

        # The base gallery is packed with expand=True. If the progress panel is
        # appended after it, Windows/Tk can squeeze the later widget to only the
        # LabelFrame title. Temporarily remove the gallery, pack a fixed-height
        # progress panel first, then let the gallery consume the remaining space.
        self.media_gallery_box = self.media_canvas.master
        self.media_gallery_box.pack_forget()

        progress_box = ttk.LabelFrame(self.media_tab, text="Progreso del proceso", padding=8, height=150)
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
        ttk.Label(row1, textvariable=self.media_product_percent, width=5).pack(side="left")

        row2 = ttk.Frame(left)
        row2.pack(fill="x", pady=(2, 2))
        ttk.Label(row2, text="Progreso general", width=15).pack(side="left")
        self.media_overall_progress = ttk.Progressbar(row2, maximum=100, mode="determinate")
        self.media_overall_progress.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self.media_overall_percent = tk.StringVar(value="0%")
        ttk.Label(row2, textvariable=self.media_overall_percent, width=5).pack(side="left")

        self.media_progress_detail = tk.StringVar(value="0 productos completados")
        ttk.Label(left, textvariable=self.media_progress_detail).pack(anchor="w", pady=(4, 0))

        self.wolf_canvas = tk.Canvas(right, width=190, height=96, highlightthickness=0)
        self.wolf_canvas.pack()
        self.wolf_caption = tk.StringVar(value="El lobo está listo para buscar")
        ttk.Label(right, textvariable=self.wolf_caption, anchor="center").pack(fill="x")
        self._draw_wolf(0, "idle")

        self.media_gallery_box.pack(fill="both", expand=True)

    @staticmethod
    def _wolf_asset_path() -> Path:
        if getattr(sys, "_MEIPASS", None):
            return Path(sys._MEIPASS) / "product_intelligence" / "assets" / "wolf_search.gif"
        return Path(__file__).resolve().parent / "assets" / "wolf_search.gif"

    def _load_wolf_gif(self):
        self._wolf_gif_frames = []
        path = self._wolf_asset_path()
        try:
            with Image.open(path) as image:
                for frame in ImageSequence.Iterator(image):
                    rgba = frame.convert("RGBA")
                    rgba.thumbnail((180, 88))
                    self._wolf_gif_frames.append(ImageTk.PhotoImage(rgba.copy()))
        except Exception:
            self._wolf_gif_frames = []
        self._wolf_gif_index = 0

    def _start_media_indices(self, indices: list[int]):
        valid_count = sum(1 for index in indices if self._identity_for_index(index) is not None)
        self._progress = BatchProgress(total=valid_count)
        self._set_progress_ui()
        self._wolf_state = "searching" if valid_count else "idle"
        return super()._start_media_indices(indices)

    def _drain_progress_events(self):
        try:
            while True:
                event = self._progress_events.get_nowait()
                self._apply_progress_event(event)
        except queue.Empty:
            pass
        self.after(150, self._drain_progress_events)

    def _apply_progress_event(self, event: dict):
        event_type = str(event.get("type") or "")
        if event_type == "batch_status":
            message = str(event.get("message") or "")
            match = re.match(r"(\d+)/(\d+)\s+—\s+(.+)", message)
            if match:
                position = max(0, int(match.group(1)) - 1)
                self._progress.start_product(position, match.group(3))
            else:
                self._progress.set_stage("searching")
            self._wolf_state = "searching"
        elif event_type == "status":
            self._progress.set_stage("searching")
            self._wolf_state = "searching"
        elif event_type == "page":
            status = str(event.get("status") or "")
            if status == "fetching":
                self._progress.set_stage("searching")
                self._wolf_state = "searching"
            elif status == "validated":
                self._progress.set_stage("extracting")
                self._wolf_state = "found"
            elif status == "rejected_identity":
                self._progress.set_stage("validating")
                self._wolf_state = "searching"
        elif event_type == "media":
            self._progress.set_stage("downloading")
            self._wolf_state = "downloading"
        elif event_type == "media_rejected":
            self._progress.set_stage("validating")
            self._wolf_state = "searching"
        elif event_type == "done":
            self._progress.set_stage("finalizing")
            self._set_progress_ui()
            self._progress.finish_product(
                downloaded=int(event.get("downloaded") or 0),
                metadata_only=int(event.get("metadata_only") or 0),
            )
            self._wolf_state = "done"
        elif event_type == "fatal":
            self._progress.finish_product(error=True)
            self._wolf_state = "error"
        elif event_type == "batch_done":
            if self._progress.total and self._progress.completed >= self._progress.total:
                self._wolf_state = "done"
            self.media_progress_title.set("Proceso multimedia completado")
        self._set_progress_ui()

    def _set_progress_ui(self):
        if not hasattr(self, "media_overall_progress"):
            return
        product = self._progress.product_percent
        overall = self._progress.overall_percent
        self.media_product_progress["value"] = product
        self.media_overall_progress["value"] = overall
        self.media_product_percent.set(f"{product}%")
        self.media_overall_percent.set(f"{overall}%")
        if self._progress.current_label:
            self.media_progress_title.set(f"{self._progress.current_label} — {self._stage_text(self._progress.current_stage)}")
        self.media_progress_detail.set(
            f"{self._progress.completed}/{self._progress.total} productos completados  ·  "
            f"{self._progress.downloaded} archivos descargados  ·  "
            f"{self._progress.metadata_only} enlaces externos  ·  {self._progress.errors} errores"
        )

    @staticmethod
    def _stage_text(stage: str) -> str:
        return {
            "queued": "pendiente",
            "searching": "buscando fuentes",
            "validating": "validando producto",
            "extracting": "revisando galería y videos",
            "downloading": "descargando multimedia",
            "finalizing": "guardando resultados",
            "done": "completado",
            "error": "con error",
        }.get(stage, stage)

    def _set_wolf_caption(self, state: str):
        if not hasattr(self, "wolf_caption"):
            return
        self.wolf_caption.set({
            "searching": "Buscando pistas del producto…",
            "found": "¡Producto encontrado! Revisando galería…",
            "downloading": "Guardando fotos y videos…",
            "done": "¡Búsqueda completada!",
            "error": "Encontré un problema; revisa el log",
            "idle": "El lobo está listo para buscar",
        }.get(state, "Buscando…"))

    def _animate_wolf(self):
        self._wolf_frame = (self._wolf_frame + 1) % 24
        if hasattr(self, "wolf_canvas") and self._wolf_gif_frames:
            self.wolf_canvas.delete("all")
            frame = self._wolf_gif_frames[self._wolf_gif_index % len(self._wolf_gif_frames)]
            self._wolf_gif_index = (self._wolf_gif_index + 1) % len(self._wolf_gif_frames)
            self.wolf_canvas.create_image(95, 46, image=frame)
            if self._wolf_state == "done":
                self.wolf_canvas.create_text(166, 16, text="✓", font=("Segoe UI", 18, "bold"))
            elif self._wolf_state == "error":
                self.wolf_canvas.create_text(166, 16, text="!", font=("Segoe UI", 18, "bold"))
            self._set_wolf_caption(self._wolf_state)
        else:
            self._draw_wolf(self._wolf_frame, self._wolf_state)
        self.after(160, self._animate_wolf)

    def _draw_wolf(self, frame: int, state: str):
        if not hasattr(self, "wolf_canvas"):
            return
        c = self.wolf_canvas
        c.delete("all")
        bounce = math.sin(frame * 0.75) * (2.5 if state in {"searching", "downloading"} else 1.0)
        x = 72 + (math.sin(frame * 0.35) * 8 if state == "searching" else 0)
        y = 46 + bounce

        c.create_line(x - 34, y + 12, x - 48, y + 2, x - 42, y - 8, width=7, smooth=True)
        c.create_oval(x - 35, y - 8, x + 28, y + 27, fill="#6f7782", outline="#31363d", width=2)
        leg = 3 if frame % 2 else -2
        c.create_line(x - 18, y + 22, x - 22 + leg, y + 38, width=5)
        c.create_line(x + 12, y + 22, x + 17 - leg, y + 38, width=5)
        c.create_polygon(x + 12, y - 10, x + 19, y - 34, x + 31, y - 13, fill="#6f7782", outline="#31363d")
        c.create_polygon(x + 30, y - 12, x + 42, y - 32, x + 48, y - 5, fill="#6f7782", outline="#31363d")
        c.create_oval(x + 8, y - 18, x + 55, y + 18, fill="#7d8691", outline="#31363d", width=2)
        c.create_oval(x + 38, y - 1, x + 63, y + 15, fill="#aeb5bc", outline="#31363d")
        c.create_oval(x + 55, y + 3, x + 62, y + 10, fill="#24282d", outline="")
        c.create_oval(x + 35, y - 7, x + 40, y - 2, fill="#111", outline="")

        if state == "searching":
            mx = 132 + math.sin(frame * 0.55) * 6
            my = 32 + math.cos(frame * 0.55) * 3
            c.create_oval(mx - 10, my - 10, mx + 10, my + 10, outline="#3a70a8", width=3)
            c.create_line(mx + 7, my + 7, mx + 18, my + 18, fill="#3a70a8", width=4)
        elif state == "found":
            c.create_text(142, 26, text="✓", font=("Segoe UI", 24, "bold"), fill="#2d7d46")
        elif state == "downloading":
            c.create_rectangle(127, 24, 159, 48, outline="#3a70a8", width=2)
            c.create_polygon(131, 44, 140, 34, 146, 40, 152, 31, 157, 44, fill="#aeb5bc", outline="")
        elif state == "done":
            c.create_text(142, 28, text="★", font=("Segoe UI", 22, "bold"), fill="#b58a26")
        elif state == "error":
            c.create_text(142, 28, text="!", font=("Segoe UI", 22, "bold"), fill="#9b3434")
        self._set_wolf_caption(state)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
