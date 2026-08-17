from __future__ import annotations

from .audit_live_ui import AuditLiveUiMixin
from .live_ui_desktop import App as LiveUiApp
from .mercadolibre_desktop import MercadoLibreDesktopMixin
from .social_video_visibility import SocialVideoVisibilityMixin


class App(MercadoLibreDesktopMixin, SocialVideoVisibilityMixin, AuditLiveUiMixin, LiveUiApp):
    """Final packaged shell: live UI, audit, OAuth and video-by-URL visibility."""


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
