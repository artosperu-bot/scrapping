import json

from product_intelligence.discovery import SearchCandidate, search_web_query
from product_intelligence.identity_bootstrap import _brand_candidate_quality
from product_intelligence.identifiers import mpn_aliases
from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import extract_page_offers
from product_intelligence import discovery, price_peru_coverage


def test_product_type_phrase_cannot_be_brand():
    assert _brand_candidate_quality("DISCO DURO", "SA400S37/960G") is False
    assert _brand_candidate_quality("SSD", "ABC/123") is False
    assert _brand_candidate_quality("COMPRA", "ABC/123") is False


def test_mpn_aliases_preserve_original_and_add_safe_separator_variants():
    aliases = mpn_aliases("ABC/123")
    assert aliases[0] == "ABC/123"
    assert "ABC123" in aliases
    assert "ABC-123" in aliases
    assert "ABC 123" in aliases
    assert len({x.casefold() for x in aliases}) == len(aliases)


def test_jsonld_sku_is_not_relabelled_as_gtin():
    identity = ProductIdentity(mpn="ABC/123")
    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Example ABC/123",
        "mpn": "ABC/123",
        "sku": "SELLER-SKU-9",
        "offers": {"@type": "Offer", "price": "199.00", "priceCurrency": "PEN", "availability": "https://schema.org/InStock"},
    }
    html = f'<html><head><title>Example ABC/123</title><script type="application/ld+json">{json.dumps(payload)}</script></head></html>'
    rows = extract_page_offers(html, "https://example.com.pe/product/abc123", identity)
    assert rows
    assert rows[0].evidence.get("gtin") in (None, "")
    assert rows[0].sku == "SELLER-SKU-9"


def test_directed_search_filters_domain_before_ranking(monkeypatch):
    raw = [
        ("https://www.plazavea.com.pe/product/wrong", "ABC/123", "ABC/123"),
        ("https://www.memorykings.pe/producto/abc123", "ABC/123", "ABC/123"),
    ]
    monkeypatch.setattr(discovery, "_provider_search", lambda *_args, **_kwargs: raw)
    rows = search_web_query(ProductIdentity(mpn="ABC/123"), '"ABC/123" site:memorykings.pe', limit=1, required_domain="memorykings.pe")
    assert rows == ["https://www.memorykings.pe/producto/abc123"]


def test_target_domain_does_not_stop_after_first_pdp(monkeypatch):
    calls = []
    first = "https://shop.example.pe/product/abc123-one"
    second = "https://shop.example.pe/product/abc123-two"

    monkeypatch.setattr(price_peru_coverage, "_queries", lambda *_: ["q1", "q2"])
    monkeypatch.setattr(price_peru_coverage, "_is_pdp", lambda *_: True)
    monkeypatch.setattr(price_peru_coverage, "_host_matches", lambda *_: True)

    def fake_search(_identity, query, **_kwargs):
        calls.append(query)
        return [first] if query == "q1" else [second]

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)
    rows = price_peru_coverage._discover_target_domain(ProductIdentity(mpn="ABC/123"), "shop.example.pe", 5)

    assert calls == ["q1", "q2"]
    assert rows == [first, second]
