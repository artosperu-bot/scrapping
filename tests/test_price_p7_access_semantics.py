from types import SimpleNamespace

from product_intelligence import price_workflow
from product_intelligence.models import ProductIdentity
from product_intelligence.price_trace import PriceCoverageTrace


IDENTITY = ProductIdentity(mpn="ABC/123", brand="ExampleBrand")


def _run_status(monkeypatch, url: str, status_code: int, title: str = "blocked"):
    events = []
    trace = PriceCoverageTrace()
    fetched = SimpleNamespace(
        final_url=url,
        html=f"<html><head><title>{title}</title></head><body>ABC/123</body></html>",
        status_code=status_code,
        method="requests",
    )
    monkeypatch.setattr(price_workflow, "fetch_page", lambda *_a, **_k: fetched)
    monkeypatch.setattr(price_workflow, "extract_page_offers", lambda *_a, **_k: [])
    rows = price_workflow._collect_web_offers([url], IDENTITY, events.append, trace=trace)
    return rows, events, trace.source_states()


def test_http_403_is_access_blocked_not_parser_zero(monkeypatch):
    url = "https://shop.example.pe/product/abc123"
    rows, _events, states = _run_status(monkeypatch, url, 403, "Just a moment...")
    state = states["Shop"]
    assert rows == []
    assert state["status"] == "FETCH_BLOCKED"
    assert state["failure_stage"] == "ACCESS"
    assert state["fetched"] is True
    assert state["fetch_ok"] is False
    assert state["parsed"] is False
    assert state["history"][-1]["detail"] == "HTTP_403"


def test_http_404_is_stale_pdp_not_parser_zero(monkeypatch):
    url = "https://shop.example.pe/product/abc123"
    rows, _events, states = _run_status(monkeypatch, url, 404, "404")
    state = states["Shop"]
    assert rows == []
    assert state["status"] == "FETCH_NOT_FOUND"
    assert state["failure_stage"] == "ACCESS"
    assert state["fetched"] is True
    assert state["fetch_ok"] is False
    assert state["parsed"] is False
    assert state["history"][-1]["detail"] == "HTTP_404"
