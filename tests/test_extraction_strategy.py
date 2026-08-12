from product_intelligence.extraction_strategy import browser_decision, extraction_plan


def test_extraction_order_starts_structured_and_keeps_ocr_out_of_normal_path():
    plan = extraction_plan()
    assert plan[0] == "structured_data"
    assert "static_html" in plan
    assert "rendered_dom" in plan
    assert "same_site_json" in plan
    assert "official_pdf" in plan
    assert "ocr" not in plan


def test_gallery_requests_browser_enrichment():
    d = browser_decision("<html><body>Product</body></html>", ["bluetooth"], media_slots=8)
    assert d.needed is True
    assert d.reason == "gallery_requested"


def test_static_page_with_good_target_coverage_does_not_force_browser():
    html = """
    <html><body>
      <dl>
        <dt>Bluetooth</dt><dd>5.4</dd>
        <dt>Battery life</dt><dd>25 h</dd>
        <dt>Connectivity</dt><dd>Wireless</dd>
        <dt>Color</dt><dd>Blue</dd>
      </dl>
    </body></html>
    """
    d = browser_decision(html, ["bluetooth", "battery life", "connectivity", "color"], media_slots=0)
    assert d.needed is False
    assert d.reason == "static_target_coverage_sufficient"


def test_low_static_target_coverage_escalates_to_browser():
    html = "<html><body><h1>Exact product</h1></body></html>"
    d = browser_decision(html, ["bluetooth", "battery life", "connectivity", "color", "package contents"], media_slots=0)
    assert d.needed is True
    assert d.reason == "static_target_coverage_low"
