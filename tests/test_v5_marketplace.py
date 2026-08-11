from product_intelligence.models import ProductIdentity, ProductRecord
from product_intelligence.marketplace_mapper import derive_name_en, derive_variation, media_rank
from product_intelligence.template_intelligence import classify_field


def record(**identity):
    return ProductRecord(identity=ProductIdentity(**identity), specifications={})


def test_name_en_is_derived_from_verified_product_name_without_invention():
    r=record(brand="Kingston", model="NV3", product_name="Kingston NV3 PCIe 4.0 NVMe SSD 500GB", mpn="SNV3S/500G", capacity="500GB", confidence=.99, match_level="EXACT")
    v=derive_name_en(r)
    assert v.value=="Kingston NV3 PCIe 4.0 NVMe SSD 500GB"
    assert v.confidence>=.95


def test_variation_capacity_only_for_exact_variant():
    r=record(brand="Kingston", model="NV3", mpn="SNV3S/500G", capacity="500GB", confidence=.99, match_level="EXACT")
    v=derive_variation(r)
    assert v.value=="500GB"
    assert v.confidence>=.9


def test_variation_not_invented_for_weak_identity():
    r=record(brand="Acme", model="X", capacity="1TB", confidence=.60, match_level="MEDIUM")
    assert derive_variation(r).value is None


def test_template_detects_name_en_and_variation_as_derivable():
    assert classify_field("NameEn #133816")[0]=="DERIVABLE"
    assert classify_field("Variación #1700")[0]=="DERIVABLE"


def test_exact_variant_image_outranks_exact_product_even_if_product_confidence_high():
    exact_variant={"scope":"EXACT_VARIANT","confidence":.91,"source":"dom:src","evidence":["mpn_match","capacity_match","strong_identifier_in_resource"]}
    exact_product={"scope":"EXACT_PRODUCT","confidence":.99,"source":"jsonld:Product.image","evidence":["model_match"]}
    assert media_rank(exact_variant)>media_rank(exact_product)


def test_structured_exact_variant_image_outranks_generic_dom_exact_variant():
    structured={"scope":"EXACT_VARIANT","confidence":.95,"source":"jsonld:Product.image","evidence":["mpn_match","capacity_match","strong_identifier_in_resource"]}
    generic={"scope":"EXACT_VARIANT","confidence":.95,"source":"dom:src","evidence":["mpn_match","capacity_match","strong_identifier_in_resource"]}
    assert media_rank(structured)>media_rank(generic)
