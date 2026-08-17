from __future__ import annotations

import os
import queue
import threading
import traceback
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .desktop import App as BaseApp
from .media_workflow import run_media_product
from .social_video_downloader import (
    VideoSelectionRequired,
    download_social_video,
    social_video_progress_text,
)


class App(BaseApp):
    """Desktop extension that keeps media discovery isolated from Excel generation."""

    def __init__(self):
        self.media_events: queue.Queue = queue.Queue()
        self.media_manual_urls: dict[int, list[str]] = {}
        self._media_current_index: int | None = None
        self._media_running = False
        self._social_video_running = False
        self._media_photo_refs: list[object] = []
        self._media_cards = 0
        super().__init__()
        self.after(150, self._drain_media_events)

    def _build(self):
        super()._build()
        self._build_media_tab()

    def _build_media_tab(self):
        self.media_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.media_tab, text="7. Fotos y videos")
        ttk.Label(self.media_tab, text="Multimedia por producto — proceso independiente del Excel", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(self.media_tab, text="URLs manuales primero → búsqueda web por Part Number/modelo → fabricante/oficial → extracción estructurada/API/HTML/Playwright → descarga validada.").pack(anchor="w", pady=(1, 7))

        upper = ttk.Panedwindow(self.media_tab, orient="horizontal")
        upper.pack(fill="x")
        left = ttk.LabelFrame(upper, text="Producto", padding=8)
        right = ttk.LabelFrame(upper, text="URLs manuales opcionales", padding=8)
        upper.add(left, weight=1); upper.add(right, weight=2)
        self.media_product_list = tk.Listbox(left, exportselection=False, height=8)
        self.media_product_list.pack(fill="both", expand=True)
        self.media_product_list.bind("<<ListboxSelect>>", self._on_media_product_select)
        ttk.Label(right, text="Una URL por línea. Se intenta antes de la búsqueda automática y siempre se valida contra el producto.").pack(anchor="w")
        self.media_urls_text = tk.Text(right, height=5, wrap="word", font=("Consolas", 9))
        self.media_urls_text.pack(fill="both", expand=True, pady=(4, 5))
        controls = ttk.Frame(right); controls.pack(fill="x")
        self.media_auto_search = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Buscar también automáticamente por Part Number/modelo", variable=self.media_auto_search).pack(side="left")
        ttk.Button(controls, text="Guardar URLs", command=self._save_media_urls).pack(side="right")
        ttk.Label(right, text="La búsqueda automática prioriza páginas oficiales. En este módulo el color no bloquea si el modelo está validado.", font=("Segoe UI", 9, "italic")).pack(anchor="w", pady=(5, 0))

        action_row = ttk.Frame(self.media_tab); action_row.pack(fill="x", pady=(8, 5))
        self.media_selected_btn = ttk.Button(action_row, text="BUSCAR Y DESCARGAR MULTIMEDIA", command=self._run_media_selected); self.media_selected_btn.pack(side="left")
        self.media_all_btn = ttk.Button(action_row, text="Procesar todos los productos", command=self._run_media_all); self.media_all_btn.pack(side="left", padx=8)
        ttk.Button(action_row, text="Abrir carpeta multimedia", command=self._open_media_folder).pack(side="left")
        self.media_status = tk.StringVar(value="Analiza un Excel para cargar los productos.")
        ttk.Label(action_row, textvariable=self.media_status, font=("Segoe UI", 9, "bold")).pack(side="left", padx=12)

        social_box = ttk.LabelFrame(self.media_tab, text="Descargar video por URL", padding=8); social_box.pack(fill="x", pady=(3, 7))
        ttk.Label(social_box, text="Pega una URL pública de YouTube/TikTok/Vimeo u otra plataforma, o una página web que contenga un video embebido. Se analizará y guardará como MP4.").pack(anchor="w")
        social_row = ttk.Frame(social_box); social_row.pack(fill="x", pady=(5, 3))
        self.social_video_url = tk.StringVar(); ttk.Entry(social_row, textvariable=self.social_video_url).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.social_video_quality = tk.StringVar(value="Mejor calidad")
        ttk.Combobox(social_row, textvariable=self.social_video_quality, values=("Mejor calidad", "1080p", "720p", "480p"), width=15, state="readonly").pack(side="left", padx=(0, 8))
        self.social_video_btn = ttk.Button(social_row, text="Descargar MP4", command=self._start_social_video_download); self.social_video_btn.pack(side="left")
        self.social_video_status = tk.StringVar(value="Listo para descargar un video por URL.")
        ttk.Label(social_box, textvariable=self.social_video_status, font=("Segoe UI", 9, "italic")).pack(anchor="w")

        gallery_box = ttk.LabelFrame(self.media_tab, text="Imágenes y videos encontrados", padding=5); gallery_box.pack(fill="both", expand=True)
        self.media_canvas = tk.Canvas(gallery_box, highlightthickness=0)
        scroll = ttk.Scrollbar(gallery_box, orient="vertical", command=self.media_canvas.yview)
        self.media_canvas.configure(yscrollcommand=scroll.set); scroll.pack(side="right", fill="y"); self.media_canvas.pack(side="left", fill="both", expand=True)
        self.media_gallery = ttk.Frame(self.media_canvas)
        self._media_window = self.media_canvas.create_window((0, 0), window=self.media_gallery, anchor="nw")
        self.media_gallery.bind("<Configure>", lambda _e: self.media_canvas.configure(scrollregion=self.media_canvas.bbox("all")))
        self.media_canvas.bind("<Configure>", lambda e: self.media_canvas.itemconfigure(self._media_window, width=e.width))

    def analyze_excel(self):
        if hasattr(self, "media_product_list"): self.media_product_list.delete(0, "end")
        self.media_manual_urls = {}; self._media_current_index = None
        super().analyze_excel()
        if self.preflight is None or not hasattr(self, "media_product_list"): return
        self.media_manual_urls = {i: list(self.manual_urls.get(i, [])) for i in range(len(self.product_rows))}
        self.media_product_list.delete(0, "end")
        for i, row in enumerate(self.product_rows):
            ident = self._identity_for_index(i)
            label = (ident.mpn or ident.ean or ident.upc or ident.gtin or ident.model or ident.product_name) if ident else row.get("model") or row.get("product_name") or f"Producto {i + 1}"
            self.media_product_list.insert("end", str(label))
        if self.product_rows:
            self.media_product_list.selection_set(0); self._on_media_product_select(); self.media_status.set(f"{len(self.product_rows)} productos listos para multimedia.")
        self._clear_media_gallery()

    def _media_selected_index(self) -> int | None:
        sel = self.media_product_list.curselection(); return int(sel[0]) if sel else None

    def _capture_media_urls(self, index: int | None):
        if index is None: return
        urls: list[str] = []
        for raw in self.media_urls_text.get("1.0", "end").splitlines():
            value = raw.strip()
            if value and value.startswith(("http://", "https://")) and value not in urls: urls.append(value)
        self.media_manual_urls[index] = urls

    def _on_media_product_select(self, _event=None):
        new_index = self._media_selected_index()
        if self._media_current_index is not None and self._media_current_index != new_index: self._capture_media_urls(self._media_current_index)
        if new_index is None: return
        self._media_current_index = new_index
        self.media_urls_text.delete("1.0", "end"); self.media_urls_text.insert("1.0", "\n".join(self.media_manual_urls.get(new_index, [])))

    def _save_media_urls(self):
        index = self._media_selected_index()
        if index is None:
            messagebox.showwarning("Multimedia", "Selecciona primero un producto."); return
        self._capture_media_urls(index); self.media_status.set(f"URLs manuales guardadas: {len(self.media_manual_urls.get(index, []))}")

    def _run_media_selected(self):
        index = self._media_selected_index()
        if index is None:
            messagebox.showwarning("Multimedia", "Selecciona primero un producto."); return
        self._save_media_urls(); self._start_media_indices([index])

    def _run_media_all(self):
        if not self.product_rows:
            messagebox.showwarning("Multimedia", "Analiza primero un Excel con productos."); return
        self._capture_media_urls(self._media_selected_index()); self._start_media_indices(list(range(len(self.product_rows))))

    def _start_media_indices(self, indices: list[int]):
        if self._media_running:
            messagebox.showinfo("Multimedia", "Ya hay una búsqueda multimedia en ejecución."); return
        valid = [(index, self._identity_for_index(index)) for index in indices if self._identity_for_index(index) is not None]
        if not valid:
            messagebox.showerror("Multimedia", "No hay productos con identidad válida para procesar."); return
        output_root = self.out.get(); auto_search = bool(self.media_auto_search.get())
        manual_urls_by_index = {index: list(self.media_manual_urls.get(index, [])) for index, _ in valid}
        self._media_running = True; self.media_selected_btn.configure(state="disabled"); self.media_all_btn.configure(state="disabled"); self._clear_media_gallery()
        self.media_status.set(f"Procesando {len(valid)} producto(s)...")

        def work():
            try:
                for pos, (index, identity) in enumerate(valid, 1):
                    label = identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name
                    self.media_events.put({"type": "batch_status", "message": f"{pos}/{len(valid)} — {label}"})
                    def on_event(event, product_index=index): self.media_events.put({**event, "product_index": product_index})
                    run_media_product(identity, output_root, manual_urls=manual_urls_by_index[index], auto_search=auto_search, max_pages=10, on_event=on_event)
            except Exception:
                self.media_events.put({"type": "fatal", "error": traceback.format_exc()})
            finally:
                self.media_events.put({"type": "batch_done"})
        threading.Thread(target=work, daemon=True).start()

    def _start_social_video_download(self):
        if self._social_video_running:
            messagebox.showinfo("Descargar video", "Ya hay una descarga de video en ejecución."); return
        url = self.social_video_url.get().strip()
        if not url:
            messagebox.showwarning("Descargar video", "Pega primero el enlace del video o de la página web."); return
        quality = self.social_video_quality.get().strip() or "Mejor calidad"
        output_dir = Path(self.out.get()) / "multimedia" / "social"; product_index = self._media_selected_index()
        self._social_video_running = True; self.social_video_btn.configure(state="disabled"); self.social_video_status.set("Preparando descarga…")

        def work():
            try:
                def on_progress(progress): self.media_events.put({"type": "social_video_progress", "progress": progress})
                result = download_social_video(url, output_dir, quality=quality, on_progress=on_progress)
                self.media_events.put({"type": "social_video_done", "product_index": product_index, "item": {"media_type": "video", "local_path": str(result.local_path), "url": result.source_url, "provider": result.provider, "title": result.title, "confidence": 1.0}})
            except VideoSelectionRequired as exc:
                candidates = [
                    {
                        "url": str(candidate.url),
                        "provider": str(candidate.provider),
                        "source_kind": str(candidate.source_kind),
                        "title": str(candidate.title or ""),
                        "score": float(candidate.score),
                    }
                    for candidate in exc.candidates[:8]
                ]
                self.media_events.put({"type": "social_video_choices", "candidates": candidates})
            except Exception as exc:
                self.media_events.put({"type": "social_video_error", "error": str(exc)})
        threading.Thread(target=work, daemon=True).start()

    def _show_social_video_choices(self, candidates: list[dict]):
        rows = list(candidates or [])[:8]
        if not rows:
            self._social_video_running = False
            self.social_video_btn.configure(state="normal")
            self.social_video_status.set("No se encontraron videos seleccionables.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Seleccionar video")
        dialog.transient(self)
        dialog.resizable(True, False)
        ttk.Label(
            dialog,
            text="La página contiene varios videos posibles. Selecciona el que deseas descargar:",
            padding=(12, 10, 12, 5),
        ).pack(anchor="w")
        listbox = tk.Listbox(dialog, exportselection=False, width=92, height=min(8, len(rows)))
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        for index, candidate in enumerate(rows, 1):
            title = str(candidate.get("title") or "").strip() or f"Video {index}"
            provider = str(candidate.get("provider") or "web")
            kind = str(candidate.get("source_kind") or "video")
            listbox.insert("end", f"{title}  ·  {provider}  ·  {kind}")
        listbox.selection_set(0)

        buttons = ttk.Frame(dialog, padding=(12, 0, 12, 10)); buttons.pack(fill="x")

        def cancel():
            dialog.destroy()
            self._social_video_running = False
            self.social_video_btn.configure(state="normal")
            self.social_video_status.set("Selección de video cancelada.")

        def choose():
            selected = listbox.curselection()
            if not selected:
                messagebox.showwarning("Seleccionar video", "Selecciona primero un video.", parent=dialog)
                return
            candidate = rows[int(selected[0])]
            candidate_url = str(candidate.get("url") or "").strip()
            if not candidate_url:
                messagebox.showerror("Seleccionar video", "El video seleccionado no tiene una URL válida.", parent=dialog)
                return
            dialog.destroy()
            self._social_video_running = False
            self.social_video_btn.configure(state="normal")
            self.social_video_url.set(candidate_url)
            self.social_video_status.set("Video seleccionado; iniciando descarga…")
            self._start_social_video_download()

        ttk.Button(buttons, text="Cancelar", command=cancel).pack(side="right")
        ttk.Button(buttons, text="Descargar seleccionado", command=choose).pack(side="right", padx=(0, 8))
        listbox.bind("<Double-1>", lambda _event: choose())
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        try:
            dialog.grab_set()
            dialog.focus_set()
        except Exception:
            pass

    def _drain_media_events(self):
        try:
            while True:
                event = self.media_events.get_nowait(); event_type = event.get("type")
                if event_type == "media":
                    self._add_media_card(event.get("item") or {}, event.get("product_index"))
                elif event_type == "social_video_progress":
                    self.social_video_status.set(social_video_progress_text(event.get("progress") or {}))
                elif event_type == "social_video_choices":
                    self._social_video_running = False; self.social_video_btn.configure(state="normal")
                    self.social_video_status.set("Se encontraron varios videos; elige uno para continuar.")
                    self._show_social_video_choices(event.get("candidates") or [])
                elif event_type == "social_video_done":
                    self._social_video_running = False; self.social_video_btn.configure(state="normal")
                    item = event.get("item") or {}; self._add_media_card(item, event.get("product_index"))
                    path = Path(str(item.get("local_path") or "video.mp4")); size_text = ""
                    try:
                        size_text = f" · {path.stat().st_size / (1024 * 1024):.1f} MB" if path.is_file() else ""
                    except OSError: pass
                    self.social_video_status.set(f"MP4 guardado: {path.name}{size_text}")
                    self.emit(f"[MEDIA SOCIAL] descargado: {item.get('local_path')}")
                elif event_type == "social_video_error":
                    self._social_video_running = False; self.social_video_btn.configure(state="normal")
                    error = str(event.get("error") or "No se pudo descargar el video."); self.social_video_status.set(error); self.emit(f"[MEDIA SOCIAL] ERROR: {error}"); messagebox.showerror("Descargar video", error)
                elif event_type == "batch_status": self.media_status.set(str(event.get("message") or "Procesando..."))
                elif event_type == "page":
                    status = event.get("status"); url = event.get("url"); self.media_status.set(f"{status}: {url}"); self.emit(f"[MEDIA] {status}: {url}")
                elif event_type == "error": self.emit(f"[MEDIA] ERROR {event.get('url')}: {event.get('error')}")
                elif event_type == "done": self.emit(f"[MEDIA] producto terminado: {event.get('downloaded', 0)} descargados, {event.get('metadata_only', 0)} enlaces/video externo")
                elif event_type == "fatal": self.emit(event.get("error") or "Error multimedia"); self.media_status.set("Error durante la búsqueda multimedia.")
                elif event_type == "batch_done":
                    self._media_running = False; self.media_selected_btn.configure(state="normal"); self.media_all_btn.configure(state="normal"); self.media_status.set(f"Terminado. {self._media_cards} elementos mostrados.")
        except queue.Empty:
            pass
        self.after(150, self._drain_media_events)

    def _clear_media_gallery(self):
        if not hasattr(self, "media_gallery"): return
        for child in self.media_gallery.winfo_children(): child.destroy()
        self._media_photo_refs.clear(); self._media_cards = 0

    def _add_media_card(self, item: dict, product_index: int | None):
        position = self._media_cards; row, col = divmod(position, 5)
        card = ttk.Frame(self.media_gallery, padding=5, relief="ridge"); card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew"); self.media_gallery.columnconfigure(col, weight=1)
        local_path = str(item.get("local_path") or ""); source_url = str(item.get("url") or ""); media_type = str(item.get("media_type") or "media")
        product_label = ""
        if product_index is not None:
            ident = self._identity_for_index(product_index)
            if ident: product_label = str(ident.mpn or ident.model or ident.product_name or "")
        rendered_image = False
        if media_type == "image" and local_path and Path(local_path).exists():
            try:
                from PIL import Image, ImageTk
                image = Image.open(local_path); image.thumbnail((190, 150), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(image); self._media_photo_refs.append(photo); ttk.Label(card, image=photo).pack(); rendered_image = True
            except Exception as exc: self.emit(f"[MEDIA] miniatura no disponible: {exc}")
        if not rendered_image:
            kind = "VIDEO" if media_type == "video" else "IMAGEN"; provider = str(item.get("provider") or "directo"); ttk.Label(card, text=f"{kind}\n{provider}", anchor="center", width=24).pack(fill="both", expand=True, pady=20)
        title = product_label or str(item.get("title") or "Producto")
        ttk.Label(card, text=title[:28], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        ttk.Label(card, text=(Path(local_path).name if local_path else source_url)[:32], font=("Segoe UI", 8)).pack(anchor="w")
        confidence = item.get("confidence")
        if confidence is not None: ttk.Label(card, text=f"confianza: {confidence}", font=("Segoe UI", 8)).pack(anchor="w")
        def open_item(_event=None, path=local_path, url=source_url): self._open_media_item(path, url)
        for widget in (card, *card.winfo_children()): widget.bind("<Double-1>", open_item)
        self._media_cards += 1

    def _open_media_item(self, local_path: str, source_url: str):
        if local_path and Path(local_path).exists():
            try: os.startfile(local_path); return
            except Exception: pass
        if source_url: webbrowser.open(source_url)

    def _open_media_folder(self):
        path = Path(self.out.get()) / "multimedia"; path.mkdir(parents=True, exist_ok=True)
        try: os.startfile(str(path))
        except Exception: messagebox.showinfo("Carpeta multimedia", str(path))


def main(): App().mainloop()

if __name__ == "__main__": main()
