import json

import keyring
import pytest

from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import extract_page_offers
from product_intelligence.price_source_capabilities import SourceCapabilityRegistry, detect_ecommerce_platform


def test_source_capability_registry_persists_observations_without_making_them_permanent_truth(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    registry.record(
        "https://shop.example.pe/product/abc123",
        platform="shopify",
        discovery_method="open_web",
        extraction_method="shopify_product_json",
        price_capable=True,
        stock_capable=True,
        seller_capable=False,
        success=True,
        category="general",
    )
    loaded = SourceCapabilityRegistry(tmp_path).get("shop.example.pe")
    assert loaded is not None
    assert loaded["country"] == "PE"
    assert loaded["platform"] == "shopify"
    assert loaded["success_count"] == 1
    assert loaded["last_observed_at"]
    assert loaded["discovery_methods"] == ["open_web"]
    assert loaded["extraction_methods"] == ["shopify_product_json"]
    assert loaded["observation_count"] == 1


def test_source_capability_failure_is_observation_not_permanent_truth(tmp_path):
    registry = SourceCapabilityRegistry(tmp_path)
    registry.record(
        "https://shop.example.pe/product/abc123",
        platform="custom",
        discovery_method="open_web",
        extraction_method="html",
        success=False,
    )
    registry.record(
        "https://shop.example.pe/product/abc123",
        platform="shopify",
        discovery_method="open_web",
        extraction_method="shopify_product_json",
        price_capable=True,
        success=True,
    )
    loaded = SourceCapabilityRegistry(tmp_path).get("shop.example.pe")
    assert loaded["platform"] == "shopify"
    assert loaded["failure_count"] == 1
    assert loaded["success_count"] == 1
    assert loaded["observation_count"] == 2
    assert loaded["success_rate"] == 0.5
    assert loaded["last_success"]
    assert loaded["extraction_methods"] == ["html", "shopify_product_json"]


def test_platform_detection_uses_family_signals_not_site_hardcoding():
    assert detect_ecommerce_platform("https://a.pe/p", '<script src="https://cdn.shopify.com/x.js"></script>') == "shopify"
    assert detect_ecommerce_platform("https://b.pe/p", '<meta name="generator" content="WooCommerce">') == "woocommerce"
    assert detect_ecommerce_platform("https://c.pe/p", '<script>window.__RUNTIME__={"account":"x"};</script> vteximg') == "vtex"
    assert detect_ecommerce_platform("https://d.pe/p", '<script type="application/ld+json">{"@type":"Product"}</script>') == "jsonld"
    assert detect_ecommerce_platform("https://e.pe/p", '<script type="text/x-magento-init">{}</script>') == "magento"
    assert detect_ecommerce_platform("https://f.pe/p", '<html><body>custom store</body></html>') == "custom"


def test_mercadolibre_token_store_turns_missing_keyring_backend_into_unconfigured(monkeypatch):
    from product_intelligence import mercadolibre_oauth as ml

    def no_backend(_key):
        raise keyring.errors.NoKeyringError("no backend")

    monkeypatch.setattr(ml, "load_value", no_backend)
    service = ml.MercadoLibreAuthService(store=ml.MercadoLibreTokenStore())
    with pytest.raises(ml.MercadoLibreAuthError) as exc:
        service.get_valid_access_token()
    assert exc.value.code == "ML_AUTH_NOT_CONFIGURED"
    assert "backend" not in str(exc.value).lower()


def _generic_rows(body: str):
    identity = ProductIdentity(brand="ExampleBrand", model="Model 123", mpn="ABC/123")
    html = f'''<html><head><title>ExampleBrand Model 123 ABC/123</title></head><body>
    <h1>ExampleBrand Model 123 ABC/123</h1>{body}</body></html>'''
    return extract_page_offers(html, "https://shop.example.pe/product/abc123", identity)


def test_generic_html_does_not_treat_installment_or_shipping_as_product_price():
    rows = _generic_rows('''
      <div>En 12 cuotas desde S/ 4.00 al mes</div>
      <div>Envío desde S/ 9.90</div>
      <div class="product-price">Precio Internet S/ 499.00</div>
    ''')
    assert len(rows) == 1
    assert rows[0].selling_price == 499.0


def test_generic_html_returns_zero_when_only_non_product_money_is_visible():
    rows = _generic_rows('''
      <div>Cuota mensual S/ 4.00</div>
      <div>Costo de envío S/ 9.90</div>
    ''')
    assert rows == []


@pytest.mark.parametrize("noise", [
    "Precio por kg S/ 4.00",
    "Cuota mensual S/ 40.00",
    "Costo de envío S/ 9.90",
    "Cupón S/ 20.00",
])
def test_generic_html_ignores_non_product_money_when_real_price_exists(noise):
    rows = _generic_rows(f'<div>{noise}</div><div>Precio Internet S/ 499.00</div>')
    assert len(rows) == 1
    assert rows[0].selling_price == 499.0


def test_generic_html_rejects_weight_prefixed_reference_price():
    rows = _generic_rows('<div>5un = 1Kg(aprox) | SKU: 0.2kg S/ 16.92 - Cancelar + Aceptar</div>')
    assert rows == []


def test_generic_html_skips_weight_prefixed_reference_price_when_real_price_exists():
    rows = _generic_rows('''
      <div>5un = 1Kg(aprox) | SKU: 0.2kg S/ 16.92 - Cancelar + Aceptar</div>
      <div>Precio Internet S/ 499.00</div>
    ''')
    assert len(rows) == 1
    assert rows[0].selling_price == 499.0


def test_generic_html_does_not_choose_list_price_over_explicit_selling_price():
    rows = _generic_rows('<div>Precio lista S/ 599.00</div><div>Precio Internet S/ 499.00</div>')
    assert len(rows) == 1
    assert rows[0].selling_price == 499.0


def test_generic_html_accepts_explicit_card_or_cash_product_price():
    card = _generic_rows('<div>Precio con tarjeta S/ 479.00</div>')
    cash = _generic_rows('<div>Precio efectivo S/ 489.00</div>')
    assert card[0].selling_price == 479.0
    assert cash[0].selling_price == 489.0
