from __future__ import annotations

from pathlib import Path
import re
import threading
from tkinter import messagebox

from .pdf_pipeline import discover_validated_review_pdfs
from .pdf_review_shell import App as BasePdfReviewApp


def review_gate_missing_indices(*, total_products: int, reviewed_mode: bool, pdf_enabled: bool, enforced_indices) -> list[int]:
    if not reviewed_mode or not pdf_enabled:
        return []
    enforced = {int(index) for index in enforced_indices}
    return [index for index in range(max(0, int(total_products))) if index not in enforced]


class App(BasePdfReviewApp):
    """Real Excel/EXE review shell: identity -> download -> validate -> review -> selection."""

    def _pdf_review_search(self):
        index = self._pdf_review_product_index()
        if index is None:
            messagebox.showinfo("Revisión PDF", "Selecciona un producto primero.")
            return
        identity = self._identity_for_index(index)
        if identity is None:
            messagebox.showerror("Revisión PDF", "El producto no tiene identidad válida.")
            return

        self.pdf_review_search_button.configure(state="disabled")
        self.pdf_review_status.set("Resolviendo identidad, buscando, descargando y validando PDFs…")
        self._pdf_review_selected[index] = set()
        self._pdf_review_enforced.discard(index)
        self._pdf_review_candidates[index] = []
        self._pdf_review_inspections[index] = {}
        self._pdf_review_refresh_tree()

        out_var = getattr(self, "out", None)
        output = str(out_var.get() if out_var is not None else "").strip()
        root = Path(output) if output else (Path.home() / "ProductIntelligence_Output")
        label = re.sub(r"[^A-Za-z0-9._-]+", "_", str(identity.mpn or identity.model or index))
        cache_dir = root / "pdf_review" / label

        def emit(line: str):
            try:
                self.after(0, lambda text=line: self.pdf_review_status.set(text))
            except Exception:
                pass

        def work():
            try:
                result = discover_validated_review_pdfs(identity, cache_dir, limit=8, timeout=10, log=emit)
                self.after(0, lambda: self._pdf_review_validated_done(index, result, None))
            except Exception as exc:
                self.after(0, lambda: self._pdf_review_validated_done(index, None, f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=work, daemon=True).start()

    def _pdf_review_validated_done(self, index, result, error: str | None):
        self.pdf_review_search_button.configure(state="normal")
        if error or result is None:
            self.pdf_review_status.set(f"Error en discovery PDF: {error or 'error desconocido'}")
            return

        candidates = [row.candidate for row in result.candidates]
        inspections = {row.candidate.url: row.inspection for row in result.candidates}
        self._pdf_review_candidates[index] = candidates
        self._pdf_review_inspections[index] = inspections
        self._pdf_review_selected[index] = set()
        self._pdf_review_enforced.discard(index)
        self._pdf_review_refresh_tree()

        resolved = result.resolved.identity
        self.pdf_review_status.set(
            f"Identidad: {resolved.brand or '-'} · {resolved.model or resolved.product_name or '-'} · "
            f"{result.validated_count} PDF(s) validados; {result.rejected_count} rechazados; "
            f"{result.duplicate_count} duplicados. Estado: NOT_REVIEWED."
        )

        if candidates and self._pdf_review_product_index() == index:
            children = self.pdf_review_tree.get_children()
            if children:
                self.pdf_review_tree.selection_set(children[0])
                self.pdf_review_tree.focus(children[0])
        elif not candidates:
            self.pdf_review_detail.set(
                "No se encontraron PDFs validados para este producto. Puedes confirmar igualmente la revisión con 0 PDFs."
            )

    def run(self):
        rows = list(getattr(self, "product_rows", []) or [])
        reviewed_mode = getattr(self, "pdf_review_mode", None) is not None and self.pdf_review_mode.get() == "reviewed"
        pdf_enabled = bool(getattr(self, "use_pdf_evidence", None) and self.use_pdf_evidence.get())
        missing = review_gate_missing_indices(
            total_products=len(rows),
            reviewed_mode=reviewed_mode,
            pdf_enabled=pdf_enabled,
            enforced_indices=getattr(self, "_pdf_review_enforced", set()),
        )
        if missing:
            first = missing[0]
            self._show_workspace("pdf_review")
            if hasattr(self, "pdf_review_product_box"):
                self.pdf_review_product_box.current(first)
                self._pdf_review_refresh_tree()
            pending = ", ".join(str(index + 1) for index in missing)
            message = (
                "Revisión PDF pendiente. Confirma una decisión para cada producto antes de ejecutar "
                f"(productos pendientes: {pending}). Confirmar 0 PDFs es válido. "
                "El modo revisado nunca activa PDF automático por falta de selección."
            )
            self.pdf_review_status.set(message)
            messagebox.showwarning("Revisión PDF pendiente", message)
            return None
        return super().run()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
