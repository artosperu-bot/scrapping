from types import SimpleNamespace

from product_intelligence import media_workflow as workflow
from product_intelligence.models import ProductIdentity


def test_validated_manufacturer_page_with_no_static_media_gets_browser_enrichment(monkeypatch, tmp_path):
    identity = ProductIdentity(brand="Acme", model="Widget Pro 7", mpn="ACM-WP7")
    static = SimpleNamespace(
        final_url="https://www.acme.example/products/widget-pro-7",
        html="<html><title>Acme Widget Pro 7 ACM-WP7</title><body>ACM-WP7 Widget Pro 7</body></html>",
        method="requests",
        network_resources=[],
    )
    browser = SimpleNamespace(
        final_url=static.final_url,
        html="""
        <html><title>Acme Widget Pro 7 ACM-WP7</title><body>
          <div class='product-media-gallery'>
            <img alt='Acme Widget Pro 7 ACM-WP7 front' src='https://cdn.acme.example/media/ACM-WP7-front-1600.jpg'>
          </div>
        </body></html>
        """,
        method="playwright",
        network_resources=[{"url": "https://cdn.acme.example/media/ACM-WP7-front-1600.jpg", "resource_type": "image"}],
    )
    calls = {"browser": 0}

    monkeypatch.setattr(workflow, "fetch_page", lambda *a, **k: static)

    def fake_browser(*args, **kwargs):
        calls["browser"] += 1
        return browser

    monkeypatch.setattr(workflow, "fetch_browser", fake_browser, raising=False)
    monkeypatch.setattr(
        workflow,
        "download_media_item",
        lambda item, _identity, _root: {**item, "downloaded": True, "local_path": str(tmp_path / "image.jpg"), "width": 1600, "height": 1600},
    )
    monkeypatch.setattr(workflow, "write_media_metadata", lambda *a, **k: None)

    rows = workflow.run_media_product(
        identity,
        tmp_path,
        manual_urls=[static.final_url],
        auto_search=False,
        max_pages=1,
    )

    assert calls["browser"] == 1
    assert len(rows) == 1
    assert rows[0]["url"].endswith("ACM-WP7-front-1600.jpg")
    assert rows[0]["official_page"] is True
    assert rows[0]["fetch_method"] == "playwright"


def test_browser_enrichment_must_revalidate_identity_before_using_media(monkeypatch, tmp_path):
    identity = ProductIdentity(brand="Acme", model="Widget Pro 7", mpn="ACM-WP7")
    static = SimpleNamespace(
        final_url="https://www.acme.example/products/widget-pro-7",
        html="<html><title>Acme Widget Pro 7 ACM-WP7</title><body>ACM-WP7 Widget Pro 7</body></html>",
        method="requests",
        network_resources=[],
    )
    wrong_browser = SimpleNamespace(
        final_url=static.final_url,
        html="<html><title>Acme Other Product ZZ-999</title><div class='product-gallery'><img src='https://cdn.acme.example/ZZ-999.jpg'></div></html>",
        method="playwright",
        network_resources=[],
    )

    monkeypatch.setattr(workflow, "fetch_page", lambda *a, **k: static)
    monkeypatch.setattr(workflow, "fetch_browser", lambda *a, **k: wrong_browser, raising=False)
    monkeypatch.setattr(workflow, "write_media_metadata", lambda *a, **k: None)

    rows = workflow.run_media_product(identity, tmp_path, manual_urls=[static.final_url], auto_search=False, max_pages=1)

    assert rows == []
