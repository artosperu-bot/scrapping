from product_intelligence import media_workflow as workflow
from product_intelligence.models import ProductIdentity


def _row(confidence=0.95, role="product_gallery", scope="EXACT_PRODUCT", conflicts=None, autofill=False):
    return {
        "url": "https://cdn.example/product.jpg",
        "media_type": "image",
        "scope": scope,
        "confidence": confidence,
        "role": role,
        "conflict_reasons": conflicts or [],
        "autofill_eligible": autofill,
    }


def test_external_media_below_095_is_rejected_even_if_previously_autofill_eligible():
    assert workflow._eligible_media(_row(confidence=0.94, autofill=True), official_page=False) is False


def test_external_media_at_095_is_accepted():
    assert workflow._eligible_media(_row(confidence=0.95), official_page=False) is True


def test_validated_official_gallery_can_accept_090():
    assert workflow._eligible_media(_row(confidence=0.90, role="product_gallery"), official_page=True) is True


def test_official_unknown_image_does_not_get_gallery_exception():
    assert workflow._eligible_media(_row(confidence=0.90, role="unknown_image"), official_page=True) is False


def test_conflicts_and_page_assets_are_always_rejected():
    assert workflow._eligible_media(_row(conflicts=["capacity_conflict"]), official_page=True) is False
    assert workflow._eligible_media(_row(role="page_asset"), official_page=True) is False


def test_official_product_page_requires_official_search_or_brand_domain():
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    assert workflow._is_official_product_page("https://www.jbl.com.pe/QUANTUM350WIRELESS-.html", identity, "official_search") is True
    assert workflow._is_official_product_page("https://www.jbl.com.pe/QUANTUM350WIRELESS-.html", identity, "manual") is True
    assert workflow._is_official_product_page("https://www.random-shop.example/q350", identity, "manual") is False
