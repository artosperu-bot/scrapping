from types import SimpleNamespace

from product_intelligence.models import ProductIdentity


def test_pdp_first_can_discover_brand_owned_landing_without_pre_resolved_domain(monkeypatch):
    from product_intelligence import pdf_review_search_strategy as strategy

    identity = ProductIdentity(brand="Acme", model="Model X", mpn="ABC123")
    raw = SimpleNamespace(url="https://acme.com/products/ABC123", title="Acme Model X ABC123")
    accepted = SimpleNamespace(
        url=raw.url,
        title=raw.title,
        likely_official=True,
        identity_score=96,
    )
    seen_queries = []

    def search(_identity, query, **_kwargs):
        seen_queries.append(query)
        return [raw]

    monkeypatch.setattr(strategy.core, "search_web_query_candidates", search)
    monkeypatch.setattr(strategy.core, "_accept_search_candidate", lambda *_args, **_kwargs: accepted)
    monkeypatch.setattr(strategy.core, "_looks_like_direct_pdf", lambda _url: False)
    monkeypatch.setattr(strategy.core, "_resolve_valid_candidates", lambda *_args, **_kwargs: ["OFFICIAL_DOC"])

    result = strategy._discover_official_pdp_documents(
        identity,
        official_domain=None,
        limit=6,
        timeout=2,
    )

    assert result == ["OFFICIAL_DOC"]
    assert seen_queries
    assert '"ABC123"' in seen_queries[0]
    assert '"Acme"' in seen_queries[0]
