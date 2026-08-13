from pathlib import Path
from types import SimpleNamespace

from product_intelligence.models import ProductIdentity
from product_intelligence.price_models import PriceOffer
from product_intelligence import price_workflow


def test_price_workflow_isolated_from_excel_and_media_engines():
    source = (Path(__file__).parents[1] / "src" / "product_intelligence" / "price_workflow.py").read_text(encoding="utf-8")
    assert "run_batch" not in source
    assert "run_media_product" not in source


def test_price_workflow_survives_adapter_failure_and_emits_done(tmp_path, monkeypatch):
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    events = []
    # This test verifies the generic fallback path in isolation. Deterministic Peru
    # probes are covered separately by test_price_peru_structured_first.py.
    monkeypatch.setattr(price_workflow, "PERU_STRUCTURED_SOURCES", ())
    monkeypatch.setattr(price_workflow, "_try_mercadolibre", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("blocked")))
    monkeypatch.setattr(price_workflow, "discover_price_sources", lambda *_a, **_k: ["https://shop.example/q350"])
    monkeypatch.setattr(price_workflow, "fetch_page", lambda *_a, **_k: SimpleNamespace(final_url="https://shop.example/q350", html="<html>ok</html>"))
    rows_from_page = [
        PriceOffer(part_number="JBLQ350WLBLKAM", brand="JBL", model="Quantum 350 Wireless", channel="Shop", seller_display_name="Seller", selling_price=299, currency="PEN", url="https://shop.example/q350", confidence=1.0, identity_match="EXACT_MPN", source_type="structured", source_method="jsonld"),
        PriceOffer(part_number="JBLQ350WLBLKAM", brand="JBL", model="Quantum 350 Wireless", channel="Chile", seller_display_name="Seller CL", selling_price=29936, currency="CLP", url="https://cl.example/q350", confidence=1.0, identity_match="EXACT_MPN", source_type="structured", source_method="jsonld"),
    ]
    monkeypatch.setattr(price_workflow, "extract_page_offers", lambda *_a, **_k: rows_from_page)
    monkeypatch.setattr(price_workflow, "save_price_run", lambda *_a, **_k: None)

    rows = price_workflow.run_price_product(identity, tmp_path, on_event=events.append)
    # Currency groups may be reordered by the presentation policy. Verify the
    # same validated offers are preserved without assuming CLP vs PEN ordering.
    assert {(r.channel, r.currency, r.selling_price) for r in rows} == {
        ("Shop", "PEN", 299),
        ("Chile", "CLP", 29936),
    }
    assert any(e.get("type") == "source" and e.get("channel") == "MercadoLibre" and e.get("status") == "error" for e in events)
    assert events[-1]["type"] == "done"
    assert events[-1]["best_by_currency"] == {"PEN": 299, "CLP": 29936}
    assert "best_price" not in events[-1]
