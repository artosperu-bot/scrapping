from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import requests

from product_intelligence import mercadolibre_oauth, price_workflow
from product_intelligence.mercadolibre_oauth import MercadoLibreAuthError, MercadoLibreAuthService
from product_intelligence.models import ProductIdentity
from product_intelligence.price_adapters import parse_mercadolibre_payload, parse_shopify_product_payload, parse_vtex_payload
from product_intelligence.price_discovery import extract_page_offers
from product_intelligence.price_identity import dedupe_offers
from product_intelligence.price_models import PriceOffer
from product_intelligence.web_fetch import FetchResult


def _identity() -> ProductIdentity:
    return ProductIdentity(brand="Acme", model="Widget Pro", mpn="ABC/123")


def _base_offer(**kwargs) -> PriceOffer:
    data = dict(
        part_number="ABC/123",
        brand="Acme",
        model="Widget Pro",
        channel="Marketplace",
        seller_display_name="Same Seller",
        selling_price=299.0,
        currency="PEN",
        url="https://market.example.pe/product/abc123",
        confidence=1.0,
        identity_match="EXACT_MPN",
        source_type="api",
        source_method="marketplace_api",
    )
    data.update(kwargs)
    return PriceOffer(**data)


def test_mercadolibre_credentials_fall_back_to_environment_when_keyring_is_unavailable(monkeypatch):
    def unavailable(_name):
        raise RuntimeError("NoKeyringError: no recommended backend")

    monkeypatch.setattr(mercadolibre_oauth, "get_key", unavailable)
    monkeypatch.setenv("MERCADOLIBRE_CLIENT_ID", "client-from-env")
    monkeypatch.setenv("MERCADOLIBRE_CLIENT_SECRET", "secret-from-env")
    monkeypatch.setenv("MERCADOLIBRE_ACCESS_TOKEN", "access-from-env")
    monkeypatch.setenv("MERCADOLIBRE_REFRESH_TOKEN", "refresh-from-env")

    service = MercadoLibreAuthService(timeout=1)

    assert service.client_id == "client-from-env"
    assert service.client_secret == "secret-from-env"
    current = service.current()
    assert current is not None
    assert current.access_token == "access-from-env"
    assert current.refresh_token == "refresh-from-env"


def test_ml_auth_failure_is_semantic_and_does_not_abort_other_price_fallbacks(monkeypatch, tmp_path):
    identity = ProductIdentity(brand="Acme", model="Widget Pro", mpn="ABC/123")
    events: list[dict] = []

    monkeypatch.setattr(price_workflow, "PERU_STRUCTURED_SOURCES", ())
    monkeypatch.setattr(price_workflow, "_try_mercadolibre", lambda *_a, **_k: (_ for _ in ()).throw(MercadoLibreAuthError("missing credentials")))
    monkeypatch.setattr(price_workflow, "discover_additional_peru_pdps", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_general_peru_retailers", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_price_sources", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "load_validated_source_urls", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "save_price_run", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_validated_source_bindings", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_channel_coverage", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow.SourceCapabilityRegistry, "save", lambda *_a, **_k: None)

    rows = price_workflow.run_price_product(identity, tmp_path, on_event=events.append, max_sources=4)

    assert rows == []
    source_event = next(e for e in events if e.get("type") == "source" and e.get("channel") == "MercadoLibre")
    assert source_event["status"] == "auth_failed"
    coverage = next(e["report"] for e in events if e.get("type") == "coverage")
    ml = next(row for row in coverage["channels"] if row["channel"] == "Mercado Libre")
    assert ml["final_status"] == "ML_API_AUTH_FAILED"
    assert ml["failure_stage"] == "AUTH"


def test_http_403_is_access_blocked_and_parser_is_not_started(monkeypatch):
    identity = _identity()
    events: list[dict] = []
    blocked = FetchResult(
        url="https://shop.example.pe/product/abc123",
        final_url="https://shop.example.pe/product/abc123",
        status_code=403,
        html="<html><title>Access denied</title></html>",
        method="requests",
    )
    monkeypatch.setattr(price_workflow, "fetch_page", lambda *_a, **_k: blocked)

    rows = price_workflow._collect_web_offers(
        ["https://shop.example.pe/product/abc123"],
        identity,
        lambda event_type, **payload: events.append({"type": event_type, **payload}),
    )

    assert rows == []
    page_events = [e for e in events if e.get("type") == "page"]
    assert any(e.get("status") == "blocked" and e.get("http_status") == 403 for e in page_events)
    assert not any(e.get("status") == "parsed" for e in page_events)


def test_jsonld_null_and_seller_sku_are_never_gtin_but_explicit_valid_gtin_is_kept():
    identity = _identity()
    bad = {
        "@context": "https://schema.org", "@type": "Product", "name": "Acme Widget Pro ABC/123",
        "mpn": "ABC/123", "sku": "SELLER-SKU-9", "gtin": "null",
        "offers": {"@type": "Offer", "price": "299", "priceCurrency": "PEN"},
    }
    good = dict(bad)
    good["gtin"] = "036000291452"
    bad_html = f"<html><head><title>Acme Widget Pro ABC/123</title><script type='application/ld+json'>{json.dumps(bad)}</script></head><body><h1>Acme Widget Pro ABC/123</h1></body></html>"
    good_html = f"<html><head><title>Acme Widget Pro ABC/123</title><script type='application/ld+json'>{json.dumps(good)}</script></head><body><h1>Acme Widget Pro ABC/123</h1></body></html>"

    bad_rows = extract_page_offers(bad_html, "https://shop.example.pe/product/abc123", identity, channel="Shop")
    good_rows = extract_page_offers(good_html, "https://shop.example.pe/product/abc123", identity, channel="Shop")

    assert bad_rows[0].sku == "SELLER-SKU-9"
    assert bad_rows[0].evidence.get("gtin") is None
    assert good_rows[0].evidence.get("gtin") == "036000291452"


def test_shopify_invalid_barcode_is_not_identity_evidence():
    payload = {
        "id": 101,
        "title": "Acme Widget Pro",
        "vendor": "Acme",
        "variants": [{"id": 202, "sku": "ABC/123", "barcode": "SELLER-SKU-9", "price": 29900, "available": True}],
    }

    rows = parse_shopify_product_payload(payload, _identity(), channel="Shop", source_url="https://shop.example.pe/products/widget")

    assert len(rows) == 1
    assert rows[0].evidence.get("gtin") is None
    assert rows[0].seller_sku == "ABC/123"


def test_vtex_multiple_sellers_keep_distinct_offer_identity_fields():
    payload = [{
        "productId": "P100",
        "productName": "Acme Widget Pro ABC/123",
        "brand": "Acme",
        "link": "/widget-pro/p",
        "items": [{
            "itemId": "SKU100",
            "nameComplete": "Acme Widget Pro ABC/123",
            "sellers": [
                {"sellerId": "SELLER-A", "sellerName": "Seller A", "commertialOffer": {"Price": 299, "ListPrice": 329, "AvailableQuantity": 4}},
                {"sellerId": "SELLER-B", "sellerName": "Seller B", "commertialOffer": {"Price": 305, "ListPrice": 329, "AvailableQuantity": 2}},
            ],
        }],
    }]

    rows = parse_vtex_payload(payload, _identity(), channel="Marketplace", source_url="https://market.example.pe")

    assert len(rows) == 2
    assert {row.seller_id for row in rows} == {"SELLER-A", "SELLER-B"}
    assert {row.marketplace_product_id for row in rows} == {"P100"}
    assert {row.seller_sku for row in rows} == {"SKU100"}
    assert all(row.direct_product_url.endswith("/widget-pro/p") for row in rows)


def test_mercadolibre_keeps_catalog_listing_and_seller_ids_separate():
    payload = {"results": [{
        "id": "MPE123",
        "catalog_product_id": "MPE-CAT-9",
        "title": "Acme Widget Pro ABC/123",
        "price": 299,
        "currency_id": "PEN",
        "permalink": "https://articulo.mercadolibre.com.pe/MPE-123-widget",
        "seller": {"id": 77, "nickname": "Seller 77"},
        "attributes": [
            {"id": "MPN", "value_name": "ABC/123"},
            {"id": "BRAND", "value_name": "Acme"},
            {"id": "MODEL", "value_name": "Widget Pro"},
        ],
    }]}

    rows = parse_mercadolibre_payload(payload, _identity())

    assert len(rows) == 1
    row = rows[0]
    assert row.marketplace_product_id == "MPE-CAT-9"
    assert row.marketplace_listing_id == "MPE123"
    assert row.seller_id == "77"
    assert row.direct_product_url == row.url


def test_dedupe_does_not_collapse_distinct_marketplace_seller_ids():
    a = _base_offer(seller_id="A", marketplace_listing_id="L1")
    b = _base_offer(seller_id="B", marketplace_listing_id="L1")

    rows = dedupe_offers([a, b])

    assert len(rows) == 2


def test_generic_html_ignores_shipping_or_installment_amount_before_product_price():
    identity = _identity()
    html = """
    <html><head><title>Acme Widget Pro ABC/123</title></head>
    <body><h1>Acme Widget Pro ABC/123</h1>
      <div>Envío desde S/ 4.00</div>
      <div>12 cuotas desde S/ 29.00</div>
      <div class='product-price'>Precio S/ 299.00</div>
    </body></html>
    """

    rows = extract_page_offers(html, "https://shop.example.pe/product/abc123", identity, channel="Shop")

    assert len(rows) == 1
    assert rows[0].selling_price == 299.0


def test_out_of_stock_valid_offer_is_preserved_not_deleted():
    row = _base_offer(availability="https://schema.org/OutOfStock", stock=0)

    assert price_workflow._is_trusted_final_offer(row) is True
