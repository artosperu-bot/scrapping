from product_intelligence import browser_search


def test_extract_pdf_urls_from_html_and_json_resolves_relative_and_escaped_urls():
    text = r'''
      <div data-download-url="/docs/spec sheet.pdf">Spec</div>
      <script>{"manual":"https:\/\/support.example.com\/files\/manual.pdf?x=1"}</script>
      <button onclick="openDoc('/assets/quick-start.PDF')">Download</button>
    '''
    rows = browser_search.extract_pdf_urls_from_text(text, "https://example.com/product/ABC")
    urls = {url for url, _ in rows}
    assert "https://example.com/docs/spec%20sheet.pdf" in urls
    assert "https://support.example.com/files/manual.pdf?x=1" in urls
    assert "https://example.com/assets/quick-start.PDF" in urls


def test_extract_pdf_urls_ignores_non_pdf_values_and_deduplicates():
    text = 'https://example.com/a.pdf https://example.com/a.pdf /not-a-document'
    rows = browser_search.extract_pdf_urls_from_text(text, "https://example.com/product")
    assert [url for url, _ in rows] == ["https://example.com/a.pdf"]


def test_extract_pdf_urls_rejects_script_noise_and_tracking_endpoints():
    text = r'''
      "https://connect.facebook.net/en_US/.pdf"
      "/static/js/.pdf"
      "/static/js/generated.pdf"
      "/static/js/file.pdf"
      "/this.pdf"
      "/i.pdf"
      "/c*e.pdf"
      "/docs/product-manual.pdf"
      "/downloads/specification-sheet.pdf"
    '''
    urls = {url for url, _ in browser_search.extract_pdf_urls_from_text(text, "https://example.com/product/ABC")}
    assert "https://example.com/docs/product-manual.pdf" in urls
    assert "https://example.com/downloads/specification-sheet.pdf" in urls
    assert not any("connect.facebook.net" in url for url in urls)
    assert not any(url.endswith("/.pdf") for url in urls)
    assert not any(url.endswith("/generated.pdf") for url in urls)
    assert not any(url.endswith("/file.pdf") for url in urls)
    assert not any(url.endswith("/this.pdf") for url in urls)
    assert not any(url.endswith("/i.pdf") for url in urls)
    assert not any("%2A" in url or "*" in url for url in urls)
