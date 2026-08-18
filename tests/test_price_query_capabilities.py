from __future__ import annotations

import json
from pathlib import Path

from product_intelligence import discovery, price_peru_coverage
from product_intelligence.models import ProductIdentity
from product_intelligence.price_source_capabilities import SourceCapabilityRegistry, detect_platform


def test_directed_queries_use_safe_separator_aliases_and_verified_brand():
    identity = ProductIdentity(brand="Acme", model="Widget Pro", mpn="ABC/123")

    queries = price_peru_coverage._queries(identity, "example.com.pe")
    joined = "\n".join(queries)

    assert '"ABC/123" site:example.com.pe' in joined
    assert '"ABC123" site:example.com.pe' in joined
    assert ('"ABC-123" site:example.com.pe' in joined or '"ABC 123" site:example.com.pe' in joined)
    assert '"ABC/123" "Acme" site:example.com.pe' in joined
    assert '"abc/123" site:example.com.pe' not in joined


def test_search_web_query_reports_raw_in_domain_and_ranked_counts(monkeypatch):
    identity = ProductIdentity(mpn="ABC/123")
    raw = [
        ("https://shop.example.com.pe/product/abc123", "ABC/123", "ABC/123"),
        ("https://other.com.pe/product/abc123", "ABC/123", "ABC/123"),
    ]
    events: list[dict] = []
    monkeypatch.setattr(discovery, "_provider_search", lambda _query, _timeout: raw)

    urls = discovery.search_web_query(
        identity,
        '"ABC/123" site:shop.example.com.pe',
        limit=5,
        timeout=1,
        on_event=events.append,
    )

    assert urls == ["https://shop.example.com.pe/product/abc123"]
    event = events[-1]
    assert event["stage"] == "QUERY_EXECUTED"
    assert event["raw_results"] == 2
    assert event["valid_in_domain"] == 1
    assert event["ranked_results"] == 1
    assert event["domain"] == "shop.example.com.pe"


def test_target_domain_reports_information_gain_and_stops_when_candidate_budget_is_full(monkeypatch):
    identity = ProductIdentity(mpn="ABC/123")
    calls: list[str] = []
    events: list[dict] = []

    def fake_search(_identity, query, limit=6, timeout=8, on_event=None, **_kwargs):
        calls.append(query)
        index = len(calls)
        url = f"https://example.com.pe/product/abc123-{index}"
        if on_event:
            on_event({"stage": "QUERY_EXECUTED", "query": query, "raw_results": 1, "valid_in_domain": 1, "ranked_results": 1, "domain": "example.com.pe"})
        return [url]

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)

    rows = price_peru_coverage._discover_target_domain(identity, "example.com.pe", 2, on_event=events.append)

    assert len(rows) == 2
    assert len(calls) == 2
    gains = [e for e in events if e.get("stage") == "QUERY_INFORMATION_GAIN"]
    assert [e["new_pdps"] for e in gains] == [1, 1]
    assert events[-1]["stage"] == "DISCOVERY_STOP"
    assert events[-1]["reason"] == "candidate_budget_full"


def test_open_peru_discovery_accepts_new_local_ecommerce_domain_without_hint(monkeypatch):
    identity = ProductIdentity(mpn="ABC/123")
    new_url = "https://nuevatienda.com.pe/producto/acme-abc123"
    monkeypatch.setattr(
        price_peru_coverage,
        "_search_query_batches",
        lambda *_args, **_kwargs: [[new_url]],
    )

    rows = price_peru_coverage.discover_general_peru_retailers(identity, limit=5)

    assert rows == [new_url]


def test_platform_detection_prefers_reusable_families():
    assert detect_platform("https://x.com.pe/p", '<script src="/arquivos/vtex.js"></script>') == "vtex"
    assert detect_platform("https://x.com.pe/products/a", '<meta name="shopify-checkout-api-token" content="x">') == "shopify"
    assert detect_platform("https://x.com.pe/product/a", '<link rel="https://api.w.org/" href="/wp-json/"><body class="woocommerce">') == "woocommerce"
    assert detect_platform("https://x.com.pe/a", '<script type="application/ld+json">{"@type":"Product"}</script>') == "jsonld"
    assert detect_platform("https://x.com.pe/a", "<html><body>custom</body></html>") == "custom"


def test_source_capability_registry_roundtrip_keeps_timestamped_observations(tmp_path: Path):
    path = tmp_path / "source_capabilities.json"
    registry = SourceCapabilityRegistry(path)
    registry.observe(
        "https://nuevatienda.com.pe/product/abc123",
        platform="shopify",
        category="general_retail",
        discovery_method="open_peru_search",
        extraction_method="shopify_product_json",
        price_capable=True,
        stock_capable=True,
        seller_capable=False,
        success=True,
    )
    registry.save()

    loaded = SourceCapabilityRegistry(path)
    row = loaded.get("nuevatienda.com.pe")

    assert row is not None
    assert row["country"] == "PE"
    assert row["platform"] == "shopify"
    assert "general_retail" in row["categories"]
    assert "open_peru_search" in row["discovery_methods"]
    assert "shopify_product_json" in row["extraction_methods"]
    assert row["price_capable"] is True
    assert row["stock_capable"] is True
    assert row["seller_capable"] is False
    assert row["observations"] == 1
    assert row["successes"] == 1
    assert row["last_observed"]
    assert row["last_success"]
