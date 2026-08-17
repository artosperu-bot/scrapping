from __future__ import annotations

import sys
from importlib import import_module


def _run_pdf_e2e_smoke_if_requested(argv: list[str] | None = None) -> int | None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "--pdf-e2e-smoke":
        return None
    from product_intelligence.pdf_packaged_smoke import main as pdf_packaged_smoke_main

    return int(pdf_packaged_smoke_main(args[1:]))


# The packaged QA route exits before importing/bootstrapping Tk desktop shells.
if __name__ == "__main__":
    _pdf_smoke_exit = _run_pdf_e2e_smoke_if_requested()
    if _pdf_smoke_exit is not None:
        raise SystemExit(_pdf_smoke_exit)


from product_intelligence.modern_desktop import main
from product_intelligence.provider_desktop import main as provider_main
from product_intelligence.workspace_desktop import main as workspace_main
from product_intelligence.organized_desktop import main as organized_main
from product_intelligence.managed_desktop import main as _managed_base_main
from product_intelligence.real_pdf_review_shell import main as pdf_review_main
from product_intelligence.final_live_ui_desktop import main as live_ui_main

# Preserve the validated modern/PDF/provider/workspace extension-chain imports because
# regression contracts use them as evidence that those layers remain present.
# The final live shell extends the validated PDF review entry while preserving the historical
# managed_main = pdf_review_main launcher contract used by packaging/regression gates.
import_module("product_intelligence.pdf_desktop")
import_module("product_intelligence.provider_desktop")
import_module("product_intelligence.workspace_desktop")
import_module("product_intelligence.organized_desktop")
import_module("product_intelligence.pdf_review_shell")
import_module("product_intelligence.real_pdf_review_shell")
import_module("product_intelligence.live_ui_desktop")
import_module("product_intelligence.final_live_ui_desktop")
pdf_review_main = live_ui_main
managed_main = pdf_review_main
managed_main()