from product_intelligence.models import ProductIdentity
from product_intelligence.media_discovery import validate_resource_identity, discover_media, build_site_profile


def test_other_capacity_image_is_rejected_for_variant():
    expected=ProductIdentity(brand="Kingston", model="NV3", mpn="SNV3S/1000G", capacity="1TB")
    scope,conf,ev,conflicts=validate_resource_identity(
        "https://media.kingston.com/kingston/product/SNV3S_500GB_angle-zm-lg.jpg",
        expected,
        found_on_validated_product_page=True,
    )
    assert scope=="UNVERIFIED"
    assert conf==0.0
    assert "capacity_conflict" in conflicts


def test_exact_variant_resource_with_mpn_and_capacity():
    expected=ProductIdentity(brand="Acme", model="X1", mpn="AX1-1TB", capacity="1TB")
    scope,conf,ev,conflicts=validate_resource_identity(
        "https://cdn.acme.test/products/AX1-1TB_X1_1TB_front.jpg",
        expected,
        found_on_validated_product_page=True,
    )
    assert scope=="EXACT_VARIANT"
    assert conf>=.98
    assert not conflicts


def test_vimeo_embedded_on_validated_page_is_product_related_but_not_variant():
    expected=ProductIdentity(brand="Kingston", model="NV3", capacity="1TB")
    html='<iframe src="https://player.vimeo.com/video/1092902068?autoplay=1&muted=1"></iframe>'
    media=discover_media(html,"https://www.kingston.com/en/ssd/nv3",expected,page_is_validated=True)
    v=[m for m in media if m["media_type"]=="video"][0]
    assert v["provider"]=="vimeo"
    assert v["scope"] in {"PRODUCT_FAMILY","EXACT_PRODUCT"}
    assert v["scope"]!="EXACT_VARIANT"


def test_site_profile_learns_external_media_hosts_without_hardcoding():
    media=[
        {"url":"https://media.brand.test/product/a.jpg","media_type":"image","confidence":.94,"provider":None},
        {"url":"https://player.vimeo.com/video/123","media_type":"video","confidence":.84,"provider":"vimeo"},
    ]
    prof=build_site_profile("https://www.brand.test/product/x",media,[])
    hosts={x["host"] for x in prof["observed_asset_hosts"]}
    assert "media.brand.test" in hosts
    assert "player.vimeo.com" in hosts
    assert prof["video_providers"]==["vimeo"]
