from product_intelligence.price_channel_registry import build_channel_coverage
from product_intelligence.price_trace import PriceCoverageTrace


def test_coverage_preserves_fetch_blocked_instead_of_no_hay():
    trace = PriceCoverageTrace()
    trace.record("Ripley", "QUERY_EXECUTED_NO_RESULT")
    trace.record("Ripley", "URL_DISCOVERED", url="https://simple.ripley.com.pe/pmp123")
    trace.record("Ripley", "FETCH_STARTED", url="https://simple.ripley.com.pe/pmp123")
    trace.record("Ripley", "FETCH_BLOCKED", url="https://simple.ripley.com.pe/pmp123", detail="HTTP 403")

    coverage = build_channel_coverage([], source_states=trace.source_states())
    ripley = next(row for row in coverage["channels"] if row["channel"] == "Ripley")

    assert ripley["status"] == "FETCH_BLOCKED"
    assert ripley["failure_stage"] == "ACCESS"
    assert ripley["searched"] is True
    assert ripley["url_found"] is True
    assert ripley["offers"] == []


def test_coverage_preserves_parser_zero_offers():
    trace = PriceCoverageTrace()
    trace.record("Falabella", "URL_DISCOVERED", url="https://www.falabella.com.pe/falabella-pe/product/123/x")
    trace.record("Falabella", "FETCH_OK", url="https://www.falabella.com.pe/falabella-pe/product/123/x")
    trace.record("Falabella", "PARSER_STARTED", url="https://www.falabella.com.pe/falabella-pe/product/123/x")
    trace.record("Falabella", "IDENTITY_ACCEPTED", url="https://www.falabella.com.pe/falabella-pe/product/123/x")
    trace.record("Falabella", "PARSER_ZERO_OFFERS", url="https://www.falabella.com.pe/falabella-pe/product/123/x")

    coverage = build_channel_coverage([], source_states=trace.source_states())
    falabella = next(row for row in coverage["channels"] if row["channel"] == "Falabella")

    assert falabella["status"] == "PARSER_ZERO_OFFERS"
    assert falabella["failure_stage"] == "PARSER_EXTRACTION"
    assert falabella["identity_valid"] is True
    assert falabella["price_found"] is False


def test_accepted_offer_is_terminal_positive_state():
    trace = PriceCoverageTrace()
    trace.record("Oechsle", "FETCH_OK")
    trace.record("Oechsle", "OFFER_ACCEPTED")
    state = trace.source_states()["Oechsle"]

    assert state["status"] == "OFFER_ACCEPTED"
    assert state["failure_stage"] is None
