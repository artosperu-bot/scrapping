from product_intelligence.models import ProductIdentity
from product_intelligence import price_peru_coverage
from product_intelligence.price_channel_registry import (
    TARGET_CHANNELS,
    build_channel_coverage,
    channel_from_url,
)
from product_intelligence.price_identity import is_peru_offer
from product_intelligence.price_models import PriceOffer


def _offer(channel, price, url, seller=None, stock=None, availability="InStock"):
    return PriceOffer(
        part_number="JBLQ350WLBLKAM",
        brand="JBL",
        model="Quantum 350 Wireless",
        channel=channel,
        seller_display_name=seller,
        selling_price=price,
        currency="PEN",
        url=url,
        confidence=1.0,
        identity_match="EXACT_MPN",
        source_type="structured",
        source_method="jsonld",
        stock=stock,
        availability=availability,
    )


def test_registry_covers_requested_peru_channels_and_normalizes_aliases():
    labels = {row.label for row in TARGET_CHANNELS}
    assert {"Falabella", "Ripley", "Mercado Libre", "Real Plaza", "Tiendas EFE", "Coolbox", "Juntoz", "Claro", "Plaza Vea", "Promart", "Oechsle", "Wong", "Metro", "Tottus", "Sodimac"} <= labels
    assert channel_from_url("https://www.falabella.com.pe/x") == "Falabella"
    assert channel_from_url("https://www.efe.com.pe/x") == "Tiendas EFE"
    assert channel_from_url("https://www.realplaza.com/x") == "Real Plaza"
    assert channel_from_url("https://tienda.claro.com.pe/x") == "Claro"


def test_registry_backed_global_domains_are_still_recognized_as_peru_market():
    assert is_peru_offer(_offer("Real Plaza", 299, "https://www.realplaza.com/producto/p")) is True
    assert is_peru_offer(_offer("Juntoz", 299, "https://juntoz.com/product/q350")) is True


def test_channel_coverage_lists_each_individual_store_instead_of_boolean_yes():
    offers = [
        _offer("Falabella", 299, "https://www.falabella.com.pe/p/1", seller="TECHNOSHOPS"),
        _offer("Memory Kings", 233.5, "https://www.memorykings.pe/producto/1", stock=2),
        _offer("Infiniti", 349, "https://www.infiniti.com.pe/shop/1", stock=4),
    ]
    report = build_channel_coverage(offers)
    falabella = next(row for row in report["channels"] if row["channel"] == "Falabella")
    ripley = next(row for row in report["channels"] if row["channel"] == "Ripley")
    assert falabella["status"] == "FOUND"
    assert falabella["offers"][0]["seller"] == "TECHNOSHOPS"
    assert falabella["offers"][0]["price"] == 299
    # No accepted Ripley offer in this report is not evidence that Ripley was searched
    # and has no product. P0 coverage semantics preserve that distinction.
    assert ripley["status"] == "NOT_SEARCHED"
    assert [row["channel"] for row in report["individual_stores"]] == ["Memory Kings", "Infiniti"]
    assert report["individual_stores"][0]["price"] == 233.5
    assert report["individual_stores"][0]["stock"] == 2
    assert report["individual_stores"][1]["price"] == 349


def test_individual_retailer_discovery_falls_back_to_brand_model_without_weakening_final_identity(monkeypatch):
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    calls = []

    def fake_search(search_identity, query, **_kwargs):
        calls.append((search_identity.mpn, query))
        if search_identity.mpn is None and "site:bigmarketperu.com" in query and "Quantum 350 Wireless" in query:
            return ["https://bigmarketperu.com/productos/audifonos-gamer-jbl-quantum-350-wireless"]
        return []

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)
    urls = price_peru_coverage.discover_general_peru_retailers(identity, limit=5)
    assert urls == ["https://bigmarketperu.com/productos/audifonos-gamer-jbl-quantum-350-wireless"]
    assert any(mpn is None and "site:bigmarketperu.com" in query for mpn, query in calls)


def test_target_channel_discovery_does_not_run_alias_when_exact_query_found_pdp(monkeypatch):
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    calls = []

    def fake_search(search_identity, query, **_kwargs):
        calls.append((search_identity.mpn, query))
        if search_identity.mpn == "JBLQ350WLBLKAM":
            return ["https://www.falabella.com.pe/falabella-pe/product/1/JBLQ350WLBLKAM/1"]
        raise AssertionError("alias fallback should not run after exact PDP discovery")

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)
    urls = price_peru_coverage.discover_additional_peru_pdps(identity, domains=("falabella.com.pe",), limit_per_domain=3)
    assert urls == ["https://www.falabella.com.pe/falabella-pe/product/1/JBLQ350WLBLKAM/1"]
    assert all(mpn == "JBLQ350WLBLKAM" for mpn, _query in calls)
