from __future__ import annotations

import queue
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import tkinter as tk
from tkinter import ttk

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
            # UI observability must never break the price engine queue.
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
        super().__init__()
        # PriceDesktop scheduled its queue drain already. Replacing the empty queue here
        # keeps the same consumer while adding worker-safe event observation.
        self.price_events = _ObservedPriceQueue(self._observe_price_event)
        self.after(200, self._refresh_price_live_counters)

    def _build_price_tab(self):
        super()._build_price_tab()
        self.price_live_counters = tk.StringVar(value="Fuentes: 0 · Revisadas: 0 · Precios válidos: 0 · Errores: 0")
        counter = ttk.Label(
            self.price_tab,
            textvariable=self.price_live_counters,
            font=("Segoe UI", 9, "bold"),
        )
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
        var = getattr(self, "price_live_counters", None)
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
        if kind == "page" and str(event.get("status") or "") in {
            "parsed",
            "error",
            "browser_retry",
            "browser_error",
        }:
            self._price_live_reviewed += 1
        if event.get("error") or (kind == "source" and str(event.get("status") or "") == "error"):
            self._price_live_errors += 1
        if update_widget:
            self._update_price_live_counter_text()

    def _append_price_audit(self, event: dict):
        message = "PRICE_EVENT " + " · ".join(
            f"{key}={value}" for key, value in event.items() if value not in (None, "")
        )
        emit = getattr(self, "emit", None)
        if callable(emit):
            emit(message)

    def _insert_price_offer(self, row: dict, label: str | None):
        key = price_offer_visual_key(row)
        if key in self._price_visual_offer_keys:
            self._append_price_audit(
                {
                    "type": "offer",
                    "status": "DUPLICATE_SKIPPED",
                    "channel": row.get("channel"),
                    "url": row.get("url"),
                }
            )
            return False
        self._price_visual_offer_keys.add(key)
        super()._insert_price_offer(row, label)
        self._price_visual_offer_count += 1
        self._update_price_live_counter_text()
        return True


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
