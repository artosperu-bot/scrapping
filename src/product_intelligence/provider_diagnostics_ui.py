from __future__ import annotations


class ProviderDiagnosticsMixin:
    """Show actionable provider diagnostics without exposing raw exception text."""

    def _finish_provider_probe(self, result, status_var, button):
        allowed = {"PROBANDO…", "CONECTADO", "RECHAZADO", "ERROR DE RED", "SIN CONFIGURAR"}
        status = result.status if result.status in allowed else "RECHAZADO"
        detail = str(getattr(result, "detail", "") or "").strip()
        status_var.set(f"{status} · {detail}" if detail else status)
        button.configure(state="normal")
