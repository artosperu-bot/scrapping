from __future__ import annotations

from types import SimpleNamespace

from product_intelligence.models import ProductIdentity
from product_intelligence.price_models import PriceOffer
from product_intelligence import price_workflow
from product_intelligence.price_trace import PriceTrace


def _offer(channel: str, url: str, *, availability: str | None = None) -> PriceOffer:
    return PriceOffer(
        part_number="ZX-4109",
        brand="Acme",
        model="Widget 4109",
        channel=channel,
        seller_display_name=channel,
        selling_price=299.0,
        currency="PEN",
        url=url,
        confidence=1.0,
        identity_match="EXACT_MPN",
        source_type="structured",
        source_method="jsonld",
        availability=availability,
    )


def test_trace_preserves_fetch_blocked_instead_of_collapsing_to_no_hay():
    trace = PriceTrace()
    trace.record("QUERY_EXECUTED", channel="Ripley", query='"ZX-4109" site:simple.ripley.com.pe')
    trace.record("URL_DISCOVERED", channel="Ripley", url="https://simple.ripley.com.pe/zx-4109-pmp1")
    trace.record("FETCH_STARTED", channel="Ripley", url="https://simple.ripley.com.pe/zx-4109-pmp1")
    trace.record("FETCH_BLOCKED", channel="Ripley", url="https://simple.ripley.com.pe/zx-4109-pmp1", http_status=403)

    coverage = trace.coverage([])
    ripley = next(row for row in coverage["channels"] if row["channel"] == "Ripley")

    assert ripley["searched"] is True
    assert ripley["url_found"] is True
    assert ripley["fetched"] is False
    assert ripley["final_status"] == "FETCH_BLOCKED"
    assert ripley["failure_stage"] == "ACCESS"
    assert "NO_HAY" not in {ripley["status"], ripley["final_status"]}


def test_trace_preserves_parser_zero_and_offer_accepted_by_source():
    trace = PriceTrace()
    falabella_url = "https://www.falabella.com.pe/falabella-pe/product/123/zx-4109/124"
    trace.record("QUERY_EXECUTED", channel="Falabella", query='"ZX-4109" site:falabella.com.pe')
    trace.record("URL_DISCOVERED", channel="Falabella", url=falabella_url)
    trace.record("FETCH_OK", channel="Falabella", url=falabella_url)
    trace.record("PARSER_STARTED", channel="Falabella", url=falabella_url)
    trace.record("PARSER_ZERO_OFFERS", channel="Falabella", url=falabella_url)

    accepted = _offer("Oechsle", "https://www.oechsle.pe/zx-4109/p", availability="https://schema.org/InStock")
    coverage = trace.coverage([accepted])
    by_channel = {row["channel"]: row for row in coverage["channels"]}

    assert by_channel["Falabella"]["final_status"] == "PARSER_ZERO_OFFERS"
    assert by_channel["Falabella"]["failure_stage"] == "PARSER_EXTRACTION"
    assert by_channel["Oechsle"]["final_status"] == "OFFER_ACCEPTED"
    assert by_channel["Oechsle"]["price_found"] is True


def test_price_workflow_resolves_partial_identity_once_before_all_price_sources(monkeypatch, tmp_path):
    input_identity = ProductIdentity(mpn="ZX-4109")
    resolved_identity = ProductIdentity(brand="Acme", model="Widget 4109", mpn="ZX-4109")
    bootstrap_calls: list[ProductIdentity] = []
    identities_seen: list[ProductIdentity] = []
    events: list[dict] = []

    def fake_bootstrap(identity, **_kwargs):
        bootstrap_calls.append(identity)
        return SimpleNamespace(
            status="RESOLVED",
            identity=resolved_identity,
            confidence=0.98,
            reason="TEST_AUTHORITY",
            official_domain_hint="acme.example",
        )

    def fake_vtex(_url, identity, _channel, timeout=12):
        identities_seen.append(identity)
        return []

    def fake_ml(identity, timeout=15):
        identities_seen.append(identity)
        return []

    monkeypatch.setattr(price_workflow, "bootstrap_identity", fake_bootstrap)
    monkeypatch.setattr(price_workflow, "PERU_STRUCTURED_SOURCES", (("Oechsle", "https://www.oechsle.pe"),))
    monkeypatch.setattr(price_workflow, "_try_vtex", fake_vtex)
    monkeypatch.setattr(price_workflow, "_try_mercadolibre", fake_ml)
    monkeypatch.setattr(price_workflow, "discover_additional_peru_pdps", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_general_peru_retailers", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_price_sources", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "load_validated_source_urls", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "save_price_run", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_validated_source_bindings", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_channel_coverage", lambda *_a, **_k: None)

    price_workflow.run_price_product(input_identity, tmp_path, on_event=events.append, max_sources=4)

    assert bootstrap_calls == [input_identity]
    assert identities_seen and all(identity is resolved_identity for identity in identities_seen)
    identity_event = next(event for event in events if event.get("type") == "identity")
    assert identity_event["input_identity"]["mpn"] == "ZX-4109"
    assert identity_event["input_identity"]["brand"] is None
    assert identity_event["resolved_identity"]["brand"] == "Acme"
    assert identity_event["status"] == "RESOLVED"


def test_unresolved_identity_continues_without_destroying_original_signal(monkeypatch):
    original = ProductIdentity(mpn="ZX-4109")
    monkeypatch.setattr(
        price_workflow,
        "bootstrap_identity",
        lambda *_a, **_k: SimpleNamespace(
            status="IDENTITY_UNRESOLVED",
            identity=ProductIdentity(mpn="ZX-4109"),
            confidence=0.0,
            reason="INSUFFICIENT_EVIDENCE",
            official_domain_hint=None,
        ),
    )

    resolved, metadata = price_workflow._resolve_price_identity(original)

    assert resolved.mpn == original.mpn
    assert resolved.brand is None
    assert metadata["status"] == "IDENTITY_UNRESOLVED"
