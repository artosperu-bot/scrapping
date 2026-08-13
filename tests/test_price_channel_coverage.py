from product_intelligence.price_channel_registry import (
    TARGET_CHANNELS,
    build_channel_coverage,
    channel_from_url,
)
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
    assert ripley["status"] == "NO_HAY"
    assert [row["channel"] for row in report["individual_stores"]] == ["Memory Kings", "Infiniti"]
    assert report["individual_stores"][0]["price"] == 233.5
    assert report["individual_stores"][0]["stock"] == 2
    assert report["individual_stores"][1]["price"] == 349
