from types import SimpleNamespace

from product_intelligence.models import ProductIdentity
from product_intelligence import price_discovery
from product_intelligence.price_discovery import discover_price_sources, extract_page_offers


def test_jsonld_product_offer_requires_valid_identity_and_extracts_seller():
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    html = '''<html><head><title>JBL Quantum 350 Wireless</title>
    <script type="application/ld+json">{
      "@context":"https://schema.org","@type":"Product","name":"JBL Quantum 350 Wireless",
      "brand":{"@type":"Brand","name":"JBL"},"mpn":"JBLQ350WLBLKAM","sku":"Q350",
      "offers":{"@type":"Offer","price":"299.00","priceCurrency":"PEN","availability":"https://schema.org/InStock","seller":{"@type":"Organization","name":"Techno Shops"},"url":"/q350"}
    }</script></head><body>JBLQ350WLBLKAM</body></html>'''
    rows = extract_page_offers(html, "https://shop.example/products/q350", identity, channel="Shop")
    assert len(rows) == 1
    assert rows[0].selling_price == 299.0
    assert rows[0].seller_display_name == "Techno Shops"
    assert rows[0].confidence == 1.0
    assert rows[0].url == "https://shop.example/q350"


def test_jsonld_wrong_mpn_is_rejected():
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    html = '''<script type="application/ld+json">{"@type":"Product","name":"JBL Quantum 360 Wireless","brand":"JBL","mpn":"JBLQ360WLBLKAM","offers":{"@type":"Offer","price":"250","priceCurrency":"PEN"}}</script>'''
    assert extract_page_offers(html, "https://shop.example/q360", identity) == []


def test_discovery_keeps_peru_sources_and_drops_foreign_generic_results(monkeypatch):
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    candidates = [
        SimpleNamespace(url="https://stereoplus.ca/jblq350wlblkam"),
        SimpleNamespace(url="https://www.falabella.com.pe/product/jblq350wlblkam"),
        SimpleNamespace(url="https://simple.ripley.com.pe/jblq350wlblkam"),
        SimpleNamespace(url="https://another.example/jblq350wlblkam"),
        SimpleNamespace(url="https://tienda-local.com.pe/jblq350wlblkam"),
    ]
    monkeypatch.setattr(price_discovery, "discover_targeted_peru_sources", lambda *_a, **_k: [])
    monkeypatch.setattr(price_discovery, "search_web", lambda *_a, **_k: candidates)
    urls = discover_price_sources(identity, limit=5)
    assert urls == [
        "https://www.falabella.com.pe/product/jblq350wlblkam",
        "https://simple.ripley.com.pe/jblq350wlblkam",
        "https://tienda-local.com.pe/jblq350wlblkam",
    ]
    assert "https://stereoplus.ca/jblq350wlblkam" not in urls
    assert "https://another.example/jblq350wlblkam" not in urls
