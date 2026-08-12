from types import SimpleNamespace

from product_intelligence.models import ProductIdentity
import product_intelligence.media_workflow as workflow


def test_manual_urls_are_processed_before_search_candidates(monkeypatch, tmp_path):
    identity = ProductIdentity(mpn="ABC123", brand="Brand", model="Model One")
    order = []

    monkeypatch.setattr(workflow, "search_web", lambda *_a, **_k: [SimpleNamespace(url="https://official/model", likely_official=True)])

    def fake_fetch(url, **kwargs):
        order.append(url)
        return SimpleNamespace(final_url=url, html="Brand Model One ABC123", network_resources=[], status_code=200, method="requests")

    monkeypatch.setattr(workflow, "fetch_page", fake_fetch)
    monkeypatch.setattr(workflow, "discover_media", lambda *_a, **_k: [])

    workflow.run_media_product(identity, tmp_path, manual_urls=["https://manual/model"], auto_search=True)
    assert order == ["https://manual/model", "https://official/model"]


def test_duplicate_manual_and_search_url_is_fetched_once(monkeypatch, tmp_path):
    identity = ProductIdentity(mpn="ABC123", brand="Brand", model="Model One")
    calls = []
    url = "https://brand.example/model"
    monkeypatch.setattr(workflow, "search_web", lambda *_a, **_k: [SimpleNamespace(url=url, likely_official=True)])
    monkeypatch.setattr(workflow, "fetch_page", lambda u, **_k: calls.append(u) or SimpleNamespace(final_url=u, html="ABC123 Brand Model One", network_resources=[], status_code=200, method="requests"))
    monkeypatch.setattr(workflow, "discover_media", lambda *_a, **_k: [])
    workflow.run_media_product(identity, tmp_path, manual_urls=[url], auto_search=True)
    assert calls == [url]


def test_fetch_enables_lazy_media_and_color_is_relaxed_only_for_media(monkeypatch, tmp_path):
    identity = ProductIdentity(mpn="ABC123", brand="Brand", model="Model One", color="Black", capacity="256 GB")
    captured = {}
    monkeypatch.setattr(workflow, "search_web", lambda *_a, **_k: [])

    def fake_fetch(url, **kwargs):
        captured["fetch_kwargs"] = kwargs
        return SimpleNamespace(final_url=url, html="ABC123 Brand Model One 256 GB", network_resources=[], status_code=200, method="playwright")

    def fake_discover(html, base_url, expected, **kwargs):
        captured["expected"] = expected
        return [{"url": "https://cdn.example/model-blue.jpg", "media_type": "image", "scope": "EXACT_PRODUCT", "confidence": 0.94, "role": "product_gallery", "autofill_eligible": True}]

    monkeypatch.setattr(workflow, "fetch_page", fake_fetch)
    monkeypatch.setattr(workflow, "discover_media", fake_discover)
    monkeypatch.setattr(workflow, "download_media_item", lambda item, *_a, **_k: {**item, "downloaded": True, "local_path": str(tmp_path / "x.jpg")})
    monkeypatch.setattr(workflow, "write_media_metadata", lambda *_a, **_k: None)

    results = workflow.run_media_product(identity, tmp_path, manual_urls=["https://brand.example/model"], auto_search=False)
    assert captured["fetch_kwargs"]["activate_lazy_media"] is True
    assert captured["fetch_kwargs"]["prefer_browser"] is True
    assert captured["expected"].color is None
    assert captured["expected"].capacity == "256 GB"
    assert results[0]["downloaded"] is True


def test_unvalidated_page_does_not_download_media(monkeypatch, tmp_path):
    identity = ProductIdentity(mpn="ABC123", brand="Brand", model="Model One")
    monkeypatch.setattr(workflow, "search_web", lambda *_a, **_k: [])
    monkeypatch.setattr(workflow, "fetch_page", lambda u, **_k: SimpleNamespace(final_url=u, html="Totally Different Product XYZ999", network_resources=[], status_code=200, method="requests"))
    called = {"discover": 0}
    monkeypatch.setattr(workflow, "discover_media", lambda *_a, **_k: called.__setitem__("discover", called["discover"] + 1) or [])
    results = workflow.run_media_product(identity, tmp_path, manual_urls=["https://wrong.example/item"], auto_search=False)
    assert results == []
    assert called["discover"] == 0


def test_hosted_video_is_kept_as_metadata(monkeypatch, tmp_path):
    identity = ProductIdentity(mpn="ABC123", brand="Brand", model="Model One")
    monkeypatch.setattr(workflow, "search_web", lambda *_a, **_k: [])
    monkeypatch.setattr(workflow, "fetch_page", lambda u, **_k: SimpleNamespace(final_url=u, html="ABC123 Brand Model One", network_resources=[], status_code=200, method="requests"))
    monkeypatch.setattr(workflow, "discover_media", lambda *_a, **_k: [{"url": "https://youtube.com/embed/demo", "media_type": "video", "provider": "youtube", "scope": "EXACT_PRODUCT", "confidence": 0.95, "role": "product_video", "autofill_eligible": True}])
    monkeypatch.setattr(workflow, "download_media_item", lambda item, *_a, **_k: {**item, "downloaded": False, "metadata_only": True, "reason": "hosted_video"})
    monkeypatch.setattr(workflow, "write_media_metadata", lambda *_a, **_k: None)
    results = workflow.run_media_product(identity, tmp_path, manual_urls=["https://brand.example/model"], auto_search=False)
    assert results[0]["metadata_only"] is True
