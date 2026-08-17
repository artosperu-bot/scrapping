from __future__ import annotations

from .audit_live_ui import AuditLiveUiMixin
from .live_ui_desktop import App as LiveUiApp


class App(AuditLiveUiMixin, LiveUiApp):
    """Final packaged shell: live rendering + structured audit + recovery."""


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
