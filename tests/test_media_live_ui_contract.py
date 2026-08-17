from product_intelligence.live_ui_desktop import App


class FakeVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = str(value)


def _app():
    app = App.__new__(App)
    app._media_live_counts = {"pages": 0, "images": 0, "videos": 0, "downloaded": 0, "rejected": 0}
    app._media_live_page_keys = set()
    app.media_live_counters = FakeVar()
    return app


def test_media_live_observer_counts_pages_media_downloads_and_rejections_truthfully():
    app = _app()
    app._observe_media_event({"type": "page", "url": "https://shop.test/p", "status": "validated"})
    app._observe_media_event({"type": "page", "url": "https://shop.test/p", "status": "validated"})
    app._observe_media_event({"type": "media", "item": {"media_type": "image", "downloaded": True, "local_path": "a.jpg"}})
    app._observe_media_event({"type": "media", "item": {"media_type": "video", "metadata_only": True}})
    app._observe_media_event({"type": "media_rejected", "url": "https://cdn.test/bad.jpg"})

    assert app._media_live_counts == {"pages": 1, "images": 1, "videos": 1, "downloaded": 1, "rejected": 1}
    assert "Páginas: 1" in app.media_live_counters.value
    assert "Imágenes: 1" in app.media_live_counters.value
    assert "Videos: 1" in app.media_live_counters.value
    assert "Descargados: 1" in app.media_live_counters.value
    assert "Rechazados: 1" in app.media_live_counters.value
    assert "%" not in app.media_live_counters.value


def test_media_live_observer_does_not_count_filtered_candidate_as_downloaded():
    app = _app()
    app._observe_media_event({"type": "media_filtered", "url": "https://cdn.test/asset.jpg"})
    assert app._media_live_counts["downloaded"] == 0
    assert app._media_live_counts["images"] == 0
    assert app._media_live_counts["rejected"] == 1


def test_media_event_contract_is_incremental_before_done():
    app = _app()
    order = []
    app._observe_media_event({"type": "media", "item": {"media_type": "image", "downloaded": True, "local_path": "a.jpg"}})
    order.append(("media", app._media_live_counts["images"]))
    app._observe_media_event({"type": "done", "downloaded": 1})
    order.append(("done", app._media_live_counts["images"]))
    assert order == [("media", 1), ("done", 1)]
