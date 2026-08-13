from product_intelligence.models import ProductIdentity
from product_intelligence.run_audit import normalize_event


def test_generic_categories_keep_their_own_part_number_in_audit():
    products = [
        ProductIdentity(brand="Lenovo", model="V15 G4", mpn="83A100ABC"),
        ProductIdentity(brand="Ulefone", model="Armor 22", mpn="ARMOR22-256"),
        ProductIdentity(brand="JBL", model="Quantum 350", mpn="JBLQ350WLBLKAM"),
        ProductIdentity(brand="Apple", model="USB-C 240W", mpn="A2794"),
        ProductIdentity(brand="Kingston", model="NV3", mpn="SNV3S-1000G"),
    ]
    for identity in products:
        row = normalize_event("media", {"type": "done", "identity": identity.model_dump()})
        assert row["part_number"] == identity.mpn
        assert row["module"] == "MEDIA"
        assert row["status"] == "DONE"


def test_price_and_media_found_events_are_module_specific():
    identity = ProductIdentity(brand="Generic", model="Model X", mpn="PN-001")
    media = normalize_event("media", {"type": "media", "identity": identity.model_dump(), "item": {"url": "https://example.com/a.jpg"}})
    price = normalize_event("price", {"type": "offer", "identity": identity.model_dump(), "offer": {"channel": "Retailer", "url": "https://example.com/p"}})
    assert media["status"] == price["status"] == "FOUND"
    assert media["module"] == "MEDIA"
    assert price["module"] == "PRICE"
