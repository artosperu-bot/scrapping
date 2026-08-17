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
