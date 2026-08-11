from product_intelligence.models import ProductIdentity
from product_intelligence.source_extract import source_evidence


def _pairs(ev):
    return {(e.attribute.lower(), str(e.normalized_value).lower()) for e in ev}


def test_source_extract_recovers_hidden_json_label_value_pairs():
    html = r'''
    <html><head><script>
    window.__PRODUCT__ = {
      "sku": "ABC-123",
      "specifications": [
        {"label": "Battery life", "value": "22 hrs"},
        {"displayName": "Bluetooth version", "displayValue": "5.3"},
        {"attribute": "Water resistance", "value": "IP68"}
      ]
    };
    </script></head><body>ABC-123 Product</body></html>
    '''
    expected = ProductIdentity(mpn="ABC-123", brand="Example")
    ev = source_evidence(html, "https://example.com/product/abc-123", expected, "EXACT", .92)
    pairs = _pairs(ev)
    assert ("battery life", "22 hrs") in pairs
    assert ("bluetooth version", "5.3") in pairs
    assert ("water resistance", "ip68") in pairs
    assert all(e.source_type == "official_source_html" for e in ev)


def test_source_extract_recovers_data_attribute_pair():
    html = '<div data-label="Autonomy" data-value="18 hours"></div>'
    expected = ProductIdentity(mpn="ABC-123")
    ev = source_evidence(html, "https://example.com/product/abc-123", expected, "EXACT", .92)
    assert ("autonomy", "18 hours") in _pairs(ev)


def test_source_extract_ignores_tracking_and_raw_urls():
    html = r'''<script type="application/json">{
      "analytics": "enabled",
      "productImage": "https://cdn.example.com/a.jpg",
      "specifications": [{"label":"Driver size","value":"40 mm"}]
    }</script>'''
    expected = ProductIdentity(mpn="ABC-123")
    ev = source_evidence(html, "https://example.com/product/abc-123", expected, "EXACT", .92)
    pairs = _pairs(ev)
    assert ("driver size", "40 mm") in pairs
    assert not any("analytics" == a for a, _ in pairs)
    assert not any(v.startswith("https://") for _, v in pairs)
