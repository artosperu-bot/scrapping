from product_intelligence.live_ui_desktop import App, price_offer_visual_key


class FakeTree:
    def __init__(self):
        self.rows = []

    def insert(self, _parent, _where, values):
        self.rows.append(values)
        return str(len(self.rows))


class FakeVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = str(value)


def _offer(**extra):
    row = {
        "channel": "Tienda A",
        "seller_display_name": "Seller",
        "selling_price": 399.0,
        "list_price": 420.0,
        "currency": "USD",
        "stock": "Disponible",
        "confidence": 0.94,
        "url": "https://shop.test/item/1?utm_source=x",
    }
    row.update(extra)
    return row


def test_price_offer_visual_key_is_stable_for_same_offer():
    a = _offer()
    b = _offer(url="https://shop.test/item/1?utm_source=y")
    assert price_offer_visual_key(a) == price_offer_visual_key(b)


def test_incremental_price_render_dedupes_visual_rows_and_records_duplicate():
    app = App.__new__(App)
    app.price_tree = FakeTree()
    app._price_visual_offer_keys = set()
    app._price_visual_offer_count = 0
    app._price_live_sources = set()
    app._price_live_reviewed = 0
    app._price_live_errors = 0
    app.price_live_counters = FakeVar()
    app._price_duplicate_events = []
    app._append_price_audit = lambda event: app._price_duplicate_events.append(event)

    assert app._insert_price_offer(_offer(), "Q350") is True
    assert len(app.price_tree.rows) == 1
    assert app._price_visual_offer_count == 1

    assert app._insert_price_offer(_offer(url="https://shop.test/item/1?utm_campaign=z"), "Q350") is False
    assert len(app.price_tree.rows) == 1
    assert app._price_visual_offer_count == 1
    assert app._price_duplicate_events[-1]["status"] == "DUPLICATE_SKIPPED"


def test_price_audit_updates_real_source_and_error_counters_without_fake_rejected_count():
    app = App.__new__(App)
    app._price_live_sources = set()
    app._price_live_reviewed = 0
    app._price_live_errors = 0
    app._price_visual_offer_count = 0
    app.price_live_counters = FakeVar()

    app._observe_price_event({"type": "source", "channel": "Falabella", "status": "ok"})
    app._observe_price_event({"type": "page", "channel": "Falabella", "status": "parsed"})
    app._observe_price_event({"type": "page", "channel": "Ripley", "status": "error", "error": "HTTP 403"})

    assert app._price_live_sources == {"Falabella", "Ripley"}
    assert app._price_live_reviewed == 2
    assert app._price_live_errors == 1
    assert "Fuentes: 2" in app.price_live_counters.value
    assert "Revisadas: 2" in app.price_live_counters.value
    assert "Precios válidos: 0" in app.price_live_counters.value
    assert "Errores: 1" in app.price_live_counters.value
    assert "%" not in app.price_live_counters.value
