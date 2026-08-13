from .run_audit import AuditedQueue


def attach(app):
    app.media_events = AuditedQueue(app.media_events, app.q, "MEDIA")
    app.price_events = AuditedQueue(app.price_events, app.q, "PRICE")
    return app


def install() -> None:
    from . import modern_desktop

    original = modern_desktop.App.__init__
    if getattr(original, "_audit_bridge_wrapped", False):
        return

    def wrapped(self, *args, **kwargs):
        original(self, *args, **kwargs)
        attach(self)
        self.emit("[AUDIT] Vista unificada activa: ejecución, multimedia y precios.")

    wrapped._audit_bridge_wrapped = True
    modern_desktop.App.__init__ = wrapped
