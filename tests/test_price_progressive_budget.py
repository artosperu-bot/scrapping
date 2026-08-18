from __future__ import annotations

from product_intelligence import price_peru_coverage
from product_intelligence.models import ProductIdentity


def test_directed_query_plan_prioritizes_original_then_compact_then_verified_brand():
    identity = ProductIdentity(brand="Acme", model="Widget Pro", mpn="ABC/123")

    queries = price_peru_coverage._queries(identity, "shop.example.com.pe")

    assert queries[0] == '"ABC/123" site:shop.example.com.pe'
    assert queries[1] == '"ABC123" site:shop.example.com.pe'
    assert queries[2] == '"ABC/123" "Acme" site:shop.example.com.pe'
    assert len(queries) == len(set(queries))


def test_target_domain_default_budget_does_not_expand_every_alias(monkeypatch):
    identity = ProductIdentity(brand="Acme", model="Widget Pro", mpn="ABC/123")
    calls: list[str] = []
    events: list[dict] = []

    def fake_search(_identity, query, **_kwargs):
        calls.append(query)
        return []

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)

    rows = price_peru_coverage._discover_target_domain(
        identity,
        "shop.example.com.pe",
        10,
        on_event=events.append,
    )

    assert rows == []
    assert len(calls) <= 3
    assert events[-1]["stage"] == "DISCOVERY_STOP"
    assert events[-1]["reason"] in {"query_budget_exhausted", "query_plan_exhausted"}


def test_open_retail_discovery_has_global_query_budget_even_when_no_query_finds_anything(monkeypatch):
    identity = ProductIdentity(brand="Acme", model="Widget Pro", mpn="ABC/123")
    calls: list[str] = []
    events: list[dict] = []

    def fake_search(_identity, query, **_kwargs):
        calls.append(query)
        return []

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)

    rows = price_peru_coverage.discover_general_peru_retailers(
        identity,
        limit=20,
        on_event=events.append,
        max_queries=14,
    )

    assert rows == []
    assert len(calls) == 14
    assert events[-1]["stage"] == "DISCOVERY_STOP"
    assert events[-1]["lane"] == "open_peru_retail"
    assert events[-1]["reason"] == "query_budget_exhausted"


def test_open_retail_stops_early_when_candidate_budget_is_filled(monkeypatch):
    identity = ProductIdentity(brand="Acme", model="Widget Pro", mpn="ABC/123")
    calls: list[str] = []
    events: list[dict] = []

    def fake_search(_identity, query, **_kwargs):
        calls.append(query)
        if len(calls) == 1:
            return [
                "https://newone.com.pe/producto/acme-abc123",
                "https://newtwo.com.pe/product/acme-abc123",
            ]
        raise AssertionError("candidate budget should stop further queries")

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)

    rows = price_peru_coverage.discover_general_peru_retailers(
        identity,
        limit=2,
        on_event=events.append,
        max_queries=14,
    )

    assert len(rows) == 2
    assert len(calls) == 1
    gain = next(event for event in events if event["stage"] == "QUERY_INFORMATION_GAIN")
    assert gain["new_domains"] == 2
    assert gain["new_pdps"] == 2
    assert events[-1]["reason"] == "candidate_budget_full"


def test_open_retail_progresses_to_compact_alias_only_when_exact_queries_have_not_saturated(monkeypatch):
    identity = ProductIdentity(brand="Acme", model="Widget Pro", mpn="ABC/123")
    calls: list[str] = []

    def fake_search(_identity, query, **_kwargs):
        calls.append(query)
        if '"ABC123"' in query:
            return ["https://compact-hit.com.pe/producto/acme-abc123"]
        return []

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)

    rows = price_peru_coverage.discover_general_peru_retailers(identity, limit=5, max_queries=8)

    assert rows == ["https://compact-hit.com.pe/producto/acme-abc123"]
    assert any('"ABC123"' in query for query in calls)
    assert len(calls) <= 8
