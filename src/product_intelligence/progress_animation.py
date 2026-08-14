from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageSequence, ImageTk


IDLE = "IDLE"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
ERROR = "ERROR"

_ASSET_DIR = Path("product_intelligence") / "assets" / "progress"
_FRAME_CACHE: dict[tuple[str, int, int, int], list[tuple[ImageTk.PhotoImage, int]]] = {}


def resource_path(name: str) -> Path:
    """Resolve a bundled or source-tree progress resource without absolute paths."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / _ASSET_DIR / name
    return Path(__file__).resolve().parent / "assets" / "progress" / name


class ProgressAnimation(ttk.Frame):
    """Small Tk-only animation view driven entirely by external process state."""

    def __init__(self, master, *, width: int = 180, height: int = 120):
        super().__init__(master)
        self._width = max(80, int(width))
        self._height = max(60, int(height))
        self._state = IDLE
        self._asset_name: str | None = None
        self._frames: list[tuple[ImageTk.PhotoImage, int]] = []
        self._frame_index = 0
        self._after_id: str | None = None

        self.canvas = tk.Canvas(
            self,
            width=self._width,
            height=self._height,
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.pack(anchor="center")
        self.caption = tk.StringVar(value="Listo")
        ttk.Label(self, textvariable=self.caption, anchor="center", justify="center").pack(fill="x", pady=(3, 0))

    @property
    def state(self) -> str:
        return self._state

    def _load_frames(self, asset_name: str) -> list[tuple[ImageTk.PhotoImage, int]]:
        root_id = id(self.winfo_toplevel())
        key = (asset_name, self._width, self._height, root_id)
        cached = _FRAME_CACHE.get(key)
        if cached is not None:
            return cached

        frames: list[tuple[ImageTk.PhotoImage, int]] = []
        with Image.open(resource_path(asset_name)) as image:
            default_duration = max(20, int(image.info.get("duration") or 80))
            for frame in ImageSequence.Iterator(image):
                rgba = frame.convert("RGBA")
                rgba.thumbnail((self._width, self._height), Image.Resampling.LANCZOS)
                duration = max(20, int(frame.info.get("duration") or default_duration))
                frames.append((ImageTk.PhotoImage(rgba.copy(), master=self), duration))
        if not frames:
            raise ValueError(f"GIF sin frames: {asset_name}")
        _FRAME_CACHE[key] = frames
        return frames

    def _cancel_tick(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show_frame(self) -> None:
        if not self._frames:
            self.canvas.delete("all")
            return
        frame, _duration = self._frames[self._frame_index % len(self._frames)]
        self.canvas.delete("all")
        self.canvas.create_image(self._width // 2, self._height // 2, image=frame, anchor="center")

    def _tick(self) -> None:
        self._after_id = None
        if self._state not in {RUNNING, COMPLETED} or not self._frames:
            return
        self._show_frame()
        _frame, duration = self._frames[self._frame_index % len(self._frames)]
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self._after_id = self.after(duration, self._tick)

    def _use_asset(self, asset_name: str, *, animate: bool) -> None:
        self._cancel_tick()
        if self._asset_name != asset_name or not self._frames:
            self._frames = self._load_frames(asset_name)
            self._asset_name = asset_name
        self._frame_index = 0
        self._show_frame()
        if animate:
            _frame, duration = self._frames[0]
            self._frame_index = 1 % len(self._frames)
            self._after_id = self.after(duration, self._tick)

    def set_running(self, text: str = "Procesando…") -> None:
        self._state = RUNNING
        self.caption.set(str(text or "Procesando…"))
        self._use_asset("processing.gif", animate=True)

    def set_completed(self, text: str = "Proceso completado") -> None:
        self._state = COMPLETED
        self.caption.set(str(text or "Proceso completado"))
        self._use_asset("completed.gif", animate=True)

    def set_error(self, text: str) -> None:
        self._state = ERROR
        self.caption.set(str(text or "Error"))
        self._use_asset("processing.gif", animate=False)

    def reset(self, text: str = "Listo") -> None:
        self._cancel_tick()
        self._state = IDLE
        self.caption.set(str(text or "Listo"))
        self.canvas.delete("all")
        self._frames = []
        self._asset_name = None
        self._frame_index = 0

    def stop(self) -> None:
        self._cancel_tick()

    def destroy(self) -> None:
        self._cancel_tick()
        super().destroy()
