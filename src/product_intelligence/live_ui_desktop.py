from __future__ import annotations

from pathlib import Path
import queue
import re
import threading
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import tkinter as tk
from tkinter import messagebox, ttk

from .part_number_pdf_search import search_product_pdfs
from .real_pdf_review_shell import App as RealPdfReviewApp


_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "msclkid", "mc_cid", "mc_eid"}


def _clean_offer_url(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
        query = [
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_QUERY_KEYS
            and not any(key.lower().startswith(prefix) for prefix in _TRACKING_QUERY_PREFIXES)
        ]
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))
    except Exception:
        return text


def price_offer_visual_key(row: dict) -> tuple[str, str, str, str, str, str]:
    """Stable visual identity for one accepted offer; ignores tracking-only URL noise."""
    price = row.get("selling_price")
    try:
        price_text = f"{float(price):.6f}"
    except (TypeError, ValueError):
        price_text = str(price or "")
    return (
        str(row.get("channel") or "").strip().casefold(),
        str(row.get("seller_display_name") or "").strip().casefold(),
        str(row.get("currency") or "").strip().upper(),
        price_text,
        str(row.get("stock") or "").strip().casefold(),
        _clean_offer_url(row.get("url")),
    )


class _ObservedPriceQueue(queue.Queue):
    """Observe engine events without touching Tk from the worker thread."""

    def __init__(self, observer):
        super().__init__()
        self._observer = observer

    def put(self, item, block=True, timeout=None):
        try:
            if isinstance(item, dict):
                self._observer(item, False)
        except Exception:
            pass
        return super().put(item, block=block, timeout=timeout)


class App(RealPdfReviewApp):
    """Final v0.10.25 live-UI shell. Business engines remain inherited and unchanged."""

    def __init__(self):
        self._price_visual_offer_keys: set[tuple[str, str, str, str, str, str]] = set()
        self._price_visual_offer_count = 0
        self._price_live_sources: set[str] = set()
        self._price_live_reviewed = 0
        self._price_live_errors = 0
        self._pdf_live_events: queue.Queue = queue.Queue()
        self._pdf_live_counts: dict[int, dict[str, int]] = {}
        super().__init__()
        self.price_events = _ObservedPriceQueue(self._observe_price_event)
        self.after(200, self._refresh_price_live_counters)
        self.after(100, self._drain_pdf_live_events)

    # ---------- Price live observability ----------
    def _build_price_tab(self):
        super()._build_price_tab()
        self.price_live_counters = tk.StringVar(value="Fuentes: 0 · Revisadas: 0 · Precios válidos: 0 · Errores: 0")
        counter = ttk.Label(self.price_tab, textvariable=self.price_live_counters, font=("Segoe UI", 9, "bold"))
        children = self.price_tab.winfo_children()
        if children:
            counter.pack(fill="x", padx=2, pady=(0, 6), before=children[0])
        else:
            counter.pack(fill="x", padx=2, pady=(0, 6))

    def _clear_price_results(self):
        self._price_visual_offer_keys.clear()
        self._price_visual_offer_count = 0
        self._price_live_sources.clear()
        self._price_live_reviewed = 0
        self._price_live_errors = 0
        result = super()._clear_price_results()
        self._update_price_live_counter_text()
        return result

    def _update_price_live_counter_text(self):
        var = self.__dict__.get("price_live_counters")
        if var is None:
            return
        var.set(
            f"Fuentes: {len(self._price_live_sources)} · "
            f"Revisadas: {self._price_live_reviewed} · "
            f"Precios válidos: {self._price_visual_offer_count} · "
            f"Errores: {self._price_live_errors}"
        )

    def _refresh_price_live_counters(self):
        try:
            self._update_price_live_counter_text()
        finally:
            self.after(200, self._refresh_price_live_counters)

    def _observe_price_event(self, event: dict, update_widget: bool = True):
        kind = str(event.get("type") or "")
        channel = str(event.get("channel") or "").strip()
        if channel and kind in {"source", "page"}:
            self._price_live_sources.add(channel)
        if kind == "page" and str(event.get("status") or "") in {"parsed", "error", "browser_retry", "browser_error"}:
            self._price_live_reviewed += 1
        if event.get("error") or (kind == "source" and str(event.get("status") or "") == "error"):
            self._price_live_errors += 1
        if update_widget:
            self._update_price_live_counter_text()

    def _append_price_audit(self, event: dict):
        message = "PRICE_EVENT " + " · ".join(f"{key}={value}" for key, value in event.items() if value not in (None, ""))
        emit = self.__dict__.get("emit")
        if not callable(emit):
            emit = getattr(type(self), "emit", None)
            if emit is not None:
                emit = lambda text, fn=emit: fn(self, text)
        if callable(emit):
            emit(message)

    def _insert_price_offer(self, row: dict, label: str | None):
        key = price_offer_visual_key(row)
        if key in self._price_visual_offer_keys:
            self._append_price_audit({"type": "offer", "status": "DUPLICATE_SKIPPED", "channel": row.get("channel"), "url": row.get("url")})
            return False
        self._price_visual_offer_keys.add(key)
        super()._insert_price_offer(row, label)
        self._price_visual_offer_count += 1
        self._update_price_live_counter_text()
        return True

    # ---------- PDF Review live observability ----------
    def _pdf_review_search(self):
        index = self._pdf_review_product_index()
        if index is None:
            messagebox.showinfo("Revisión PDF", "Selecciona un producto primero.")
            return
        identity = self._identity_for_index(index)
        if identity is None:
            messagebox.showerror("Revisión PDF", "El producto no tiene identidad válida.")
            return
        primary = str(identity.mpn or identity.ean or identity.upc or identity.gtin or "").strip()
        if not primary:
            messagebox.showerror("Revisión PDF", "El producto no tiene MPN/EAN/UPC/GTIN utilizable.")
            return

        self.pdf_review_search_button.configure(state="disabled")
        self.pdf_review_status.set(f"Resolviendo identidad y buscando PDFs: {primary}…")
        self._pdf_review_selected[index] = set()
        self._pdf_review_enforced.discard(index)
        self._pdf_review_candidates[index] = []
        self._pdf_review_inspections[index] = {}
        self._pdf_live_counts[index] = {"found": 0, "validated": 0, "rejected": 0, "duplicates": 0, "downloaded": 0}
        self._pdf_review_refresh_tree()

        out_var = self.__dict__.get("out")
        output = str(out_var.get() if out_var is not None else "").strip()
        root = Path(output) if output else (Path.home() / "ProductIntelligence_Output")
        label = re.sub(r"[^A-Za-z0-9._-]+", "_", primary)
        cache_dir = root / "pdf_review" / label

        def queue_log(line: str):
            self._pdf_live_events.put((index, {"type": "log", "message": str(line)}))

        def queue_event(event: dict):
            self._pdf_live_events.put((index, event))

        def work():
            try:
                result = search_product_pdfs(
                    cache_dir,
                    mpn=identity.mpn,
                    ean=identity.ean,
                    upc=identity.upc,
                    gtin=identity.gtin,
                    brand=identity.brand,
                    model=identity.model,
                    product_name=identity.product_name,
                    limit=8,
                    timeout=10,
                    log=queue_log,
                    on_event=queue_event,
                )
                self._pdf_live_events.put((index, {"type": "final_result", "result": result}))
            except Exception as exc:
                self._pdf_live_events.put((index, {"type": "final_result", "error": f"{type(exc).__name__}: {exc}"}))

        threading.Thread(target=work, daemon=True).start()

    def _drain_pdf_live_events(self):
        try:
            while True:
                index, event = self._pdf_live_events.get_nowait()
                try:
                    self._apply_pdf_live_event(index, event)
                except Exception as exc:
                    status = self.__dict__.get("pdf_review_status")
                    if status is not None:
                        status.set(f"Error actualizando Revisión PDF: {type(exc).__name__}: {exc}")
        except queue.Empty:
            pass
        finally:
            self.after(100, self._drain_pdf_live_events)

    def _apply_pdf_live_event(self, index: int, event: dict):
        kind = str(event.get("type") or "")
        counts = self._pdf_live_counts.setdefault(index, {"found": 0, "validated": 0, "rejected": 0, "duplicates": 0, "downloaded": 0})

        if kind == "candidate":
            counts["found"] += 1
        elif kind == "download" and str(event.get("status") or "") == "FINISHED":
            counts["downloaded"] += 1
        elif kind == "validated" and event.get("row") is not None:
            row = event["row"]
            url = str(row.candidate.url or "")
            candidates = self._pdf_review_candidates.setdefault(index, [])
            if not any(str(item.url or "") == url for item in candidates):
                candidates.append(row.candidate)
                self._pdf_review_inspections.setdefault(index, {})[url] = row.inspection
                self._pdf_review_selected.setdefault(index, set())
                self._pdf_review_enforced.discard(index)
                counts["validated"] += 1
                try:
                    if self._pdf_review_product_index() == index:
                        self._pdf_review_refresh_tree()
                except Exception:
                    pass
        elif kind == "rejected":
            counts["rejected"] += 1
        elif kind == "duplicate":
            counts["duplicates"] += 1
        elif kind == "identity":
            discovered = event.get("discovered")
            if discovered is not None:
                counts["found"] = max(counts["found"], int(discovered))
        elif kind == "log":
            status = self.__dict__.get("pdf_review_status")
            if status is not None:
                status.set(str(event.get("message") or "Buscando PDFs…"))
            return
        elif kind == "final_result":
            result = event.get("result")
            error = event.get("error")
            super()._pdf_review_validated_done(index, result, str(error) if error else None)
            return

        status = self.__dict__.get("pdf_review_status")
        if status is not None:
            stage = str(event.get("stage") or kind or "SEARCH").replace("_", " ")
            status.set(
                f"{stage} · candidatos: {counts['found']} · descargados: {counts['downloaded']} · "
                f"válidos: {counts['validated']} · rechazados: {counts['rejected']} · duplicados: {counts['duplicates']}"
            )


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
