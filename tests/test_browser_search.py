from product_intelligence.browser_search import _extract_result_rows


def test_extract_result_rows_returns_external_links_only():
    rows = _extract_result_rows([
        {"href": "https://www.jbl.com/JBLQ350WLBLKAM.html", "text": "JBL Quantum 350", "snippet": "Official JBL"},
        {"href": "https://www.bing.com/search?q=x", "text": "Bing", "snippet": ""},
        {"href": "https://support.jbl.com/manual.pdf", "text": "Manual PDF", "snippet": "PDF"},
    ])
    assert [row[0] for row in rows] == [
        "https://www.jbl.com/JBLQ350WLBLKAM.html",
        "https://support.jbl.com/manual.pdf",
    ]
