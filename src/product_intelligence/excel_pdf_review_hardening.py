from __future__ import annotations

from typing import Iterable

from .models import ProductIdentity


def _has_descriptive_model(identity: ProductIdentity) -> bool:
    strong = {
        _compact(value)
        for value in (identity.mpn, identity.ean, identity.upc, identity.gtin, identity.sku)
        if value
    }
    for value in (identity.model, identity.product_name):
        text = str(value or "").strip()
        if text and _compact(text) not in strong:
            return True
    return False


def _compact(value: str | None) -> str:
    import re
    from .normalize import key_norm

    return re.sub(r"[^a-z0-9]", "", key_norm(value or ""))


def prepare_document_identity(identity: ProductIdentity, timeout: int = 8) -> tuple[ProductIdentity, str | None]:
    """Enrich code-only Excel identities before document discovery.

    The existing identity bootstrap remains the single resolver. This adapter only
    makes sure PDF discovery actually uses it when Excel provides an MPN/GTIN as
    both the identifier and the apparent model.
    """
    if identity.brand and _has_descriptive_model(identity):
        return identity, None

    try:
        from .identity_bootstrap import bootstrap_identity

        result = bootstrap_identity(
            identity,
            limit_per_query=14,
            timeout=max(5, min(int(timeout or 8), 8)),
        )
    except Exception:
        return identity, None

    if str(getattr(result, "status", "")).upper() != "RESOLVED":
        return identity, None

    resolved = getattr(result, "identity", None)
    if resolved is None or not getattr(resolved, "brand", None):
        return identity, None

    # The bootstrap may enrich brand/model while the Excel row remains the
    # authoritative owner of strong identifiers. Never lose those identifiers.
    updates = {}
    for field in ("mpn", "ean", "upc", "gtin", "sku", "variant", "color", "region"):
        source_value = getattr(identity, field, None)
        if source_value and not getattr(resolved, field, None):
            updates[field] = source_value
    if updates:
        resolved = resolved.model_copy(update=updates)

    domain = str(getattr(result, "official_domain_hint", "") or "").strip() or None
    return resolved, domain


def review_gate_missing_indices(
    *,
    total_products: int,
    reviewed_mode: bool,
    pdf_enabled: bool,
    enforced_indices: Iterable[int],
) -> list[int]:
    """Return products that still need an explicit PDF review decision."""
    if not reviewed_mode or not pdf_enabled:
        return []
    enforced = {int(index) for index in enforced_indices}
    return [index for index in range(max(0, int(total_products))) if index not in enforced]


def install() -> None:
    """Install the final EXE integration without duplicating discovery engines."""
    from tkinter import messagebox

    from . import batch as batch_module
    from . import document_discovery as document_module
    from . import pdf_review as review_module
    from . import pdf_review_shell as shell_module

    if getattr(document_module, "_excel_pdf_identity_hardening", False):
        return

    base_discover = document_module.discover_product_documents

    def enriched_discover_product_documents(identity, *args, **kwargs):
        timeout = int(kwargs.get("timeout", 8) or 8)
        effective, domain_hint = prepare_document_identity(identity, timeout=timeout)
        if not kwargs.get("official_domain") and domain_hint:
            kwargs["official_domain"] = domain_hint
        return base_discover(effective, *args, **kwargs)

    # Patch every imported binding used by the packaged desktop flow. The actual
    # resolver stays document_discovery.discover_product_documents; only its input
    # identity is enriched first.
    document_module.prepare_document_identity = prepare_document_identity
    document_module.discover_product_documents = enriched_discover_product_documents
    batch_module.discover_product_documents = enriched_discover_product_documents
    review_module.discover_product_documents = enriched_discover_product_documents

    BaseApp = shell_module.App

    class HardenedPdfReviewApp(BaseApp):
        def run(self):
            rows = list(getattr(self, "product_rows", []) or [])
            reviewed_mode = (
                getattr(self, "pdf_review_mode", None) is not None
                and self.pdf_review_mode.get() == "reviewed"
            )
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
                    f"(productos pendientes: {pending}). Puedes confirmar 0 PDFs si no quieres usar PDF "
                    "para un producto. Si deseas procesamiento PDF automático, cambia el modo a Automático."
                )
                if hasattr(self, "pdf_review_status"):
                    self.pdf_review_status.set(message)
                messagebox.showwarning("Revisión PDF pendiente", message)
                return None
            return super().run()

    shell_module.review_gate_missing_indices = review_gate_missing_indices
    shell_module.App = HardenedPdfReviewApp
    document_module._excel_pdf_identity_hardening = True
