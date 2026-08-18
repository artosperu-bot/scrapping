from pathlib import Path

from product_intelligence.models import ProductIdentity
from product_intelligence.price_identity_resolution import PriceIdentityResolution
from product_intelligence.price_models import PriceOffer
from product_intelligence.price_trace import PriceCoverageTrace
from product_intelligence import price_workflow


def _offer(channel="Oechsle"):
    return PriceOffer(
        part_number="ABC/123", brand="ExampleBrand", model="Model 123",
        channel=channel, seller_display_name="Seller", selling_price=199.0,
        currency="PEN", url="https://shop.example.pe/product/abc123",
        confidence=1.0, identity_match="EXACT_MPN", source_type="structured", source_method="jsonld",
    )


def test_run_price_product_resolves_identity_before_discovery_and_preserves_input(monkeypatch, tmp_path):
    original = ProductIdentity(mpn="ABC/123")
    resolved = ProductIdentity(mpn="ABC/123", brand="ExampleBrand", model="Model 123")
    observed = {"discover": [], "events": []}

    monkeypatch.setattr(price_workflow, "resolve_price_identity", lambda identity: PriceIdentityResolution(
        input_identity=identity.model_copy(deep=True), identity=resolved, status="RESOLVED",
        confidence=.95, reason="PAGE_BACKED_IDENTITY_RESOLUTION", evidence_backed=True,
    ))
    monkeypatch.setattr(price_workflow, "PERU_STRUCTURED_SOURCES", ())
    monkeypatch.setattr(price_workflow, "load_validated_source_urls", lambda *_: [])
    monkeypatch.setattr(price_workflow, "_try_mercadolibre", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_additional_peru_pdps", lambda identity, **_k: observed["discover"].append(identity) or [])
    monkeypatch.setattr(price_workflow, "discover_general_peru_retailers", lambda identity, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_price_sources", lambda identity, **_k: [])
    monkeypatch.setattr(price_workflow, "save_price_run", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_validated_source_bindings", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_channel_coverage", lambda *_a, **_k: None)

    price_workflow.run_price_product(original, tmp_path, on_event=observed["events"].append)

    assert observed["discover"] and observed["discover"][0].brand == "ExampleBrand"
    identity_event = next(event for event in observed["events"] if event["type"] == "identity")
    assert identity_event["input_identity"]["mpn"] == "ABC/123"
    assert identity_event["resolved_identity"]["brand"] == "ExampleBrand"
    assert identity_event["resolution_status"] == "RESOLVED"


def test_collect_web_offers_records_parser_zero_without_claiming_not_found(monkeypatch):
    identity = ProductIdentity(mpn="ABC/123")
    trace = PriceCoverageTrace()
    url = "https://simple.ripley.com.pe/product/abc123"
    monkeypatch.setattr(price_workflow, "_parse_page_with_dynamic_retry", lambda *_a, **_k: ("<html></html>", []))
    monkeypatch.setattr(price_workflow, "_augment_page_rows", lambda *_a, **_k: [])

    rows = price_workflow._collect_web_offers([url], identity, lambda *_a, **_k: None, trace=trace)
    state = trace.source_states()["Ripley"]

    assert rows == []
    assert state["status"] == "PARSER_ZERO_OFFERS"
    assert state["url_found"] is True
    assert state["fetch_ok"] is True
    assert state["parsed"] is True


def test_run_price_product_builds_coverage_from_trace(monkeypatch, tmp_path):
    original = ProductIdentity(mpn="ABC/123", brand="ExampleBrand", model="Model 123")
    captured = {}

    monkeypatch.setattr(price_workflow, "resolve_price_identity", lambda identity: PriceIdentityResolution(
        input_identity=identity.model_copy(deep=True), identity=identity.model_copy(deep=True), status="RESOLVED",
        confidence=1.0, reason="BRAND_PROVIDED", evidence_backed=True,
    ))
    monkeypatch.setattr(price_workflow, "PERU_STRUCTURED_SOURCES", (("Oechsle", "https://www.oechsle.pe"),))
    monkeypatch.setattr(price_workflow, "load_validated_source_urls", lambda *_: [])
    monkeypatch.setattr(price_workflow, "_try_vtex", lambda *_a, **_k: [_offer()])
    monkeypatch.setattr(price_workflow, "_try_mercadolibre", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_additional_peru_pdps", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_general_peru_retailers", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_price_sources", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "save_price_run", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_validated_source_bindings", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_channel_coverage", lambda *_a, **_k: None)

    original_builder = price_workflow.build_channel_coverage
    def capture_builder(offers, **kwargs):
        captured["source_states"] = kwargs.get("source_states")
        return original_builder(offers, **kwargs)
    monkeypatch.setattr(price_workflow, "build_channel_coverage", capture_builder)

    rows = price_workflow.run_price_product(original, tmp_path)
    assert rows
    assert captured["source_states"]["Oechsle"]["status"] == "OFFER_ACCEPTED"
