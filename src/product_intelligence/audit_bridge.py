from .run_audit import AuditedQueue


def attach(app):
    app.media_events = AuditedQueue(app.media_events, app.q, "MEDIA")
    app.price_events = AuditedQueue(app.price_events, app.q, "PRICE")
    return app
