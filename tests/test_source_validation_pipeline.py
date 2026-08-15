import pytest

import product_intelligence.pipeline as pipeline_module
from product_intelligence.models import ProductIdentity
from product_intelligence.pipeline import ProductPipeline
from product_intelligence.web_fetch import FetchResult


def _fetch(url: str, html: str) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        html=html,
        method="requests",
    )


def test_category_page_with_target_product_is_rejected(monkeypatch):
    url = "https://brand.example/headphones"
    html = '''
    <html><head><title>All Headphones</title>
    <script type="application/ld+json">{"@type":"ItemList","itemListElement":[]}</script>
    </head><body><h1>Headphones</h1>
    <div class="product-card" data-product-id="1">ABC-100</div>
    <div class="product-card" data-product-id="2">ABC-200</div>
    <div class="product-card" data-product-id="3">ABC-300</div>
    </body></html>
    '''
    monkeypatch.setattr(pipeline_module, "fetch_page", lambda *a, **k: _fetch(url, html))
    with pytest.raises(ValueError, match="PAGE_TYPE_NOT_MATERIAL"):
        ProductPipeline().process_url(ProductIdentity(brand="Brand", model="X100", mpn="ABC-100"), url, browser_fallback=False)


def test_update_page_is_rejected_even_if_identifier_is_present(monkeypatch):
    url = "https://brand.example/support/X100/update"
    html = '''
    <html><head><title>Software Update</title></head>
    <body><h1>Notify Update</h1><p>Model X100 MPN ABC-100</p></body></html>
    '''
    monkeypatch.setattr(pipeline_module, "fetch_page", lambda *a, **k: _fetch(url, html))
    with pytest.raises(ValueError, match="PAGE_TYPE_NOT_MATERIAL"):
        ProductPipeline().process_url(ProductIdentity(brand="Brand", model="X100", mpn="ABC-100"), url, browser_fallback=False)


def test_different_product_on_same_brand_is_rejected(monkeypatch):
    url = "https://brand.example/products/model-26-ultra"
    html = '''
    <html><head><title>Brand Model 26 Ultra</title>
    <script type="application/ld+json">{
      "@context":"https://schema.org","@type":"Product","brand":{"@type":"Brand","name":"Brand"},
      "name":"Brand Model 26 Ultra","model":"Model 26 Ultra"
    }</script></head><body><h1>Brand Model 26 Ultra</h1>
    <table><tr><th>Weight</th><td>300 g</td></tr></table></body></html>
    '''
    monkeypatch.setattr(pipeline_module, "fetch_page", lambda *a, **k: _fetch(url, html))
    with pytest.raises(ValueError, match="IDENTITY_CONFLICT"):
        ProductPipeline().process_url(ProductIdentity(brand="Brand", model="Model 22"), url, browser_fallback=False)


def test_brand_token_hostname_does_not_create_manufacturer(monkeypatch):
    url = "https://brandfixpros.example/products/abc-100"
    html = '''
    <html><head><title>Brand X100 ABC-100</title>
    <script type="application/ld+json">{
      "@context":"https://schema.org","@type":"Product","brand":{"@type":"Brand","name":"Brand"},
      "name":"Brand X100","model":"X100","mpn":"ABC-100","weight":"200 g"
    }</script></head><body><h1>Brand X100</h1>
    <table><tr><th>Weight</th><td>200 g</td></tr></table></body></html>
    '''
    monkeypatch.setattr(pipeline_module, "fetch_page", lambda *a, **k: _fetch(url, html))
    rec = ProductPipeline().process_url(
        ProductIdentity(brand="Brand", model="X100", mpn="ABC-100"),
        url,
        official_domain="brandfixpros.example",
        browser_fallback=False,
    )
    assert rec.fetch["source_class"] == "secondary"
    assert rec.fetch["source_decision"]["authority"] != "manufacturer"


def test_multiple_independent_ownership_signals_allow_manufacturer(monkeypatch):
    url = "https://www.brand.example/products/abc-100"
    html = '''
    <html><head><title>Brand X100</title><link rel="canonical" href="https://www.brand.example/products/abc-100" />
    <script type="application/ld+json">[
      {"@context":"https://schema.org","@type":"Organization","name":"Brand"},
      {"@context":"https://schema.org","@type":"Product","brand":{"@type":"Brand","name":"Brand"},
       "name":"Brand X100","model":"X100","mpn":"ABC-100","weight":"200 g"}
    ]</script></head><body><h1>Brand X100</h1>
    <table><tr><th>Weight</th><td>200 g</td></tr></table>
    <a href="/products/a">A</a><a href="/products/b">B</a><a href="/products/c">C</a>
    <footer>© 2026 Brand. All rights reserved.</footer></body></html>
    '''
    monkeypatch.setattr(pipeline_module, "fetch_page", lambda *a, **k: _fetch(url, html))
    rec = ProductPipeline().process_url(ProductIdentity(brand="Brand", model="X100", mpn="ABC-100"), url, browser_fallback=False)
    assert rec.fetch["source_class"] == "manufacturer"
    assert rec.fetch["source_decision"]["authority"] == "manufacturer"
    assert rec.fetch["source_decision"]["identity"] == "EXACT"
