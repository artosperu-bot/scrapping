from product_intelligence.pdf_search_trace import PdfSearchTrace, format_trace_lines


def test_pdf_search_trace_tracks_queries_results_and_downloads():
    trace = PdfSearchTrace(product_key="JBLQ350WLBLKAM")
    trace.emit("PDF_SEARCH_QUERY", query="JBLQ350WLBLKAM pdf", transport="http")
    trace.emit("PDF_SEARCH_HTTP_RESULT", result_count=0)
    trace.emit("PDF_SEARCH_BROWSER_RESULT", result_count=8)
    trace.emit("PDF_LINK_DISCOVERED", url="https://example.com/spec.pdf")
    trace.emit("PDF_DOWNLOAD_OK", url="https://example.com/spec.pdf", bytes=1200)

    summary = trace.summary()
    assert summary["queries"] == 1
    assert summary["browser_results"] == 8
    assert summary["pdf_links"] == 1
    assert summary["downloads_ok"] == 1


def test_trace_lines_never_hide_zero_result_stage():
    trace = PdfSearchTrace("JBLQ350WLBLKAM")
    trace.emit("PDF_SEARCH_QUERY", query="JBLQ350WLBLKAM pdf", transport="http")
    trace.emit("PDF_SEARCH_HTTP_RESULT", result_count=0)
    trace.emit("PDF_SEARCH_BROWSER_FALLBACK", query="JBLQ350WLBLKAM pdf")
    trace.emit("PDF_SEARCH_BROWSER_RESULT", result_count=8)
    text = "\n".join(format_trace_lines(trace))
    assert "JBLQ350WLBLKAM pdf" in text
    assert "HTTP" in text and "0" in text
    assert "BROWSER" in text and "8" in text
