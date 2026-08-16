import json

from product_intelligence.models import ProductIdentity
from product_intelligence.price_models import PriceOffer
from product_intelligence import price_history, price_workflow


def identity(mpn="JBLQ350WLBLKAM", model="Quantum 350 Wireless"):
    return ProductIdentity(brand="JBL", model=model, mpn=mpn)


def offer(url, match="EXACT_MPN", price=299.0, channel="Shop Peru"):
    return PriceOffer(
        part_number="JBLQ350WLBLKAM",
        brand="JBL",
        model="Quantum 350 Wireless",
        channel=channel,
        seller_display_name=channel,
        selling_price=price,
        currency="PEN",
        url=url,
        confidence=1.0,
        identity_match=match,
        source_type="structured",
        source_method="jsonld",
    )


def test_source_memory_learns_only_strong_identity_and_dedupes(tmp_path):
    ident = identity()
    price_history.save_validated_source_bindings(
        tmp_path,
        ident,
        [
            offer("https://a.com.pe/p/1", "EXACT_MPN"),
            offer("https://a.com.pe/p/1", "EXACT_MPN", 289),
            offer("https://b.com.pe/p/2", "BRAND_MODEL"),
            offer("https://weak.com.pe/p/3", "PROBABLE_MODEL"),
        ],
    )

    assert price_history.load_validated_source_urls(tmp_path, ident) == [
        "https://a.com.pe/p/1",
        "https://b.com.pe/p/2",
    ]
    payload = json.loads((tmp_path / "price_intelligence" / "source_bindings.json").read_text(encoding="utf-8"))
    rows = next(iter(payload["products"].values()))
    assert len(rows) == 2
    assert {row["identity_match"] for row in rows} == {"EXACT_MPN", "BRAND_MODEL"}


def test_source_memory_isolated_by_product_identity(tmp_path):
    jbl = identity()
    other = ProductIdentity(brand="Dell", model="P2422H", mpn="P2422H")
    price_history.save_validated_source_bindings(tmp_path, jbl, [offer("https://a.com.pe/p/1")])

    assert price_history.load_validated_source_urls(tmp_path, other) == []
    assert price_history.load_validated_source_urls(tmp_path, jbl) == ["https://a.com.pe/p/1"]


def test_source_memory_corrupt_json_fails_closed(tmp_path):
    base = tmp_path / "price_intelligence"
    base.mkdir(parents=True)
    (base / "source_bindings.json").write_text("{broken", encoding="utf-8")

    assert price_history.load_validated_source_urls(tmp_path, identity()) == []


def test_warm_price_path_revalidates_learned_sources_and_skips_expensive_discovery(tmp_path, monkeypatch):
    ident = identity()
    learned = "https://known.com.pe/q350"
    fresh = offer(learned, "EXACT_MPN", 299, "Known")
    saved = []

    monkeypatch.setattr(price_workflow, "load_validated_source_urls", lambda *_a, **_k: [learned])
    monkeypatch.setattr(price_workflow, "_refresh_learned_sources", lambda *_a, **_k: [fresh])
    monkeypatch.setattr(price_workflow, "PERU_STRUCTURED_SOURCES", ())
    monkeypatch.setattr(price_workflow, "_try_mercadolibre", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_general_peru_retailers", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_additional_peru_pdps", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("targeted discovery should not run on healthy warm path")))
    monkeypatch.setattr(price_workflow, "discover_price_sources", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("generic discovery should not run on healthy warm path")))
    monkeypatch.setattr(price_workflow, "save_price_run", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_channel_coverage", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_validated_source_bindings", lambda _root, _identity, rows: saved.extend(rows))

    rows = price_workflow.run_price_product(ident, tmp_path)

    assert [(row.channel, row.selling_price) for row in rows] == [("Known", 299)]
    assert saved and saved[0].url == learned


def test_weak_warm_path_falls_back_to_full_discovery(tmp_path, monkeypatch):
    ident = identity()
    learned = "https://stale.com.pe/q350"
    fallback_url = "https://fresh.com.pe/q350"
    fallback_offer = offer(fallback_url, "EXACT_MPN", 319, "Fresh")
    calls = {"targeted": 0, "generic": 0}

    monkeypatch.setattr(price_workflow, "load_validated_source_urls", lambda *_a, **_k: [learned])
    monkeypatch.setattr(price_workflow, "_refresh_learned_sources", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "PERU_STRUCTURED_SOURCES", ())
    monkeypatch.setattr(price_workflow, "_try_mercadolibre", lambda *_a, **_k: [])
    monkeypatch.setattr(price_workflow, "discover_general_peru_retailers", lambda *_a, **_k: [])

    def targeted(*_a, **_k):
        calls["targeted"] += 1
        return [fallback_url]

    def generic(*_a, **_k):
        calls["generic"] += 1
        return []

    monkeypatch.setattr(price_workflow, "discover_additional_peru_pdps", targeted)
    monkeypatch.setattr(price_workflow, "discover_price_sources", generic)
    monkeypatch.setattr(price_workflow, "_parse_page_with_dynamic_retry", lambda *_a, **_k: ("<html></html>", [fallback_offer]))
    monkeypatch.setattr(price_workflow, "save_price_run", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_channel_coverage", lambda *_a, **_k: None)
    monkeypatch.setattr(price_workflow, "save_validated_source_bindings", lambda *_a, **_k: None)

    rows = price_workflow.run_price_product(ident, tmp_path)

    assert calls == {"targeted": 1, "generic": 1}
    assert [(row.channel, row.selling_price) for row in rows] == [("Fresh", 319)]
