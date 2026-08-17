from __future__ import annotations

from .audit_live_ui import AuditLiveUiMixin
from .live_ui_desktop import App as LiveUiApp
from .mercadolibre_desktop import MercadoLibreDesktopMixin


class App(MercadoLibreDesktopMixin, AuditLiveUiMixin, LiveUiApp):
    """Final packaged shell: live rendering + audit + automatic Mercado Libre OAuth."""


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
