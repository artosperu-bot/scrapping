from product_intelligence.html_extract import extract_page


def test_official_document_hubs_and_pdfs_are_discovered_separately():
    html = """
    <html><body>
      <a href='/support/downloads'>Documents & Downloads</a>
      <a href='/manuals/user.pdf'>User Manual</a>
      <a href='/specs/specsheet.pdf'>Spec Sheet</a>
    </body></html>
    """
    page = extract_page(html, "https://maker.example/product")
    assert "https://maker.example/support/downloads" in page["document_links"]
    assert "https://maker.example/manuals/user.pdf" in page["pdfs"]
    assert "https://maker.example/specs/specsheet.pdf" in page["pdfs"]
    assert all(not x.lower().endswith(".pdf") for x in page["document_links"])
