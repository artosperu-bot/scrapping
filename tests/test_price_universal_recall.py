from __future__ import annotations

import json

from product_intelligence import discovery, price_peru_coverage
from product_intelligence.discovery import SearchCandidate
from product_intelligence.identity_bootstrap import resolve_identity_from_candidates
from product_intelligence.models import ProductIdentity
from product_intelligence.price_channel_registry import build_channel_coverage
from product_intelligence.price_discovery import extract_page_offers


def test_empty_coverage_preserves_not_searched_instead_of_no_hay():
    coverage = build_channel_coverage([])
    statuses = {row["status"] for row in coverage["channels"]}
    assert "NO_HAY" not in statuses
    assert statuses == {"NOT_SEARCHED"}


def test_generic_product_type_cannot_become_brand_from_cross_source_serp_noise():
    identity = ProductIdentity(mpn="ZX-4109")
    candidates = [
        SearchCandidate(
            "https://one.example/zx-4109",
            "Disco Duro ZX-4109 960GB",
            "Compra disco duro ZX-4109 con envio",
        ),
        SearchCandidate(
            "https://two.example/zx-4109",
            "Disco Duro ZX-4109 SSD",
            "Producto disco duro ZX-4109 disponible",
        ),
        SearchCandidate(
            "https://three.example/zx-4109",
            "Disco Duro ZX-4109 SATA",
            "Precio del disco duro ZX-4109",
        ),
    ]

    result = resolve_identity_from_candidates(identity, candidates)

    assert result.identity.brand is None
    assert result.status == "IDENTITY_UNRESOLVED"


def test_jsonld_seller_sku_never_becomes_gtin_evidence():
    identity = ProductIdentity(mpn="ZX-4109")
    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Acme ZX-4109",
        "mpn": "ZX-4109",
        "sku": "SELLER-SKU-77",
        "brand": {"@type": "Brand", "name": "Acme"},
        "offers": {
            "@type": "Offer",
            "price": "299.00",
            "priceCurrency": "PEN",
            "availability": "https://schema.org/InStock",
        },
    }
    html = f"<html><head><title>Acme ZX-4109</title><script type='application/ld+json'>{json.dumps(payload)}</script></head><body><h1>Acme ZX-4109</h1></body></html>"

    offers = extract_page_offers(html, "https://shop.example.pe/product/zx-4109", identity, channel="Shop")

    assert len(offers) == 1
    assert offers[0].sku == "SELLER-SKU-77"
    assert offers[0].evidence.get("gtin") is None


def test_directed_site_query_filters_wrong_domains_before_ranking(monkeypatch):
    identity = ProductIdentity(mpn="ABC/123")
    raw = [
        (
            "https://www.plazavea.com.pe/product/abc123",
            "ABC/123 technical specifications product page",
            "ABC/123 technical specifications",
        ),
        (
            "https://www.memorykings.pe/producto/abc123",
            "ABC/123 product",
            "ABC/123",
        ),
    ]
    monkeypatch.setattr(discovery, "_provider_search", lambda _query, _timeout: raw)

    urls = discovery.search_web_query(identity, '"ABC/123" site:memorykings.pe', limit=1, timeout=1)

    assert urls == ["https://www.memorykings.pe/producto/abc123"]


def test_target_domain_continues_while_later_query_adds_new_pdp(monkeypatch):
    identity = ProductIdentity(mpn="ABC/123")
    calls: list[str] = []

    def fake_search(_identity, query, limit=6, timeout=8, **_kwargs):
        calls.append(query)
        if len(calls) == 1:
            return ["https://www.falabella.com.pe/falabella-pe/product/100/abc123/100"]
        if len(calls) == 2:
            return ["https://www.falabella.com.pe/falabella-pe/product/200/abc123/200"]
        return []

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)

    rows = price_peru_coverage._discover_target_domain(identity, "falabella.com.pe", 4)

    assert len(calls) >= 2
    assert rows[:2] == [
        "https://www.falabella.com.pe/falabella-pe/product/100/abc123/100",
        "https://www.falabella.com.pe/falabella-pe/product/200/abc123/200",
    ]


def test_retail_query_plan_includes_safe_separator_alias_without_case_only_duplicates():
    identity = ProductIdentity(mpn="ABC/123")

    queries = price_peru_coverage._general_retail_queries(identity)
    text = "\n".join(queries)

    assert '"ABC/123"' in text
    assert '"ABC123"' in text
    assert '"ABC-123"' in text or '"ABC 123"' in text
    assert '"abc/123"' not in text
