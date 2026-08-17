from __future__ import annotations

from .audit_live_ui import AuditLiveUiMixin
from .live_ui_desktop import App as LiveUiApp
from .mercadolibre_desktop import MercadoLibreDesktopMixin
from .pdf_review_provider_ui import PdfReviewProviderVisibilityMixin


class App(MercadoLibreDesktopMixin, PdfReviewProviderVisibilityMixin, AuditLiveUiMixin, LiveUiApp):
    """Final packaged shell: live rendering + audit + OAuth + reviewed-PDF provider visibility."""


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
