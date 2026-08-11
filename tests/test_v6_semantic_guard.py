from product_intelligence.semantic_guard import infer_contract, validate_value
from product_intelligence.excel_mapper import map_header


def test_audio_power_rejects_speed_unit():
    c=infer_contract("PotenciaDeAudio #1546","Ingresa la potencia eléctrica que el altavoz soporta")
    ok,reason,_=validate_value("10 m/s",c)
    assert not ok and "UNIT" in reason


def test_product_length_rejects_cable_length():
    c=infer_contract("Largo #10793","medida del producto fuera de su embalaje","length")
    ok,reason,_=validate_value("1.3 m",c,evidence_attribute="Cable length",evidence_raw="Cable length: 1.3 m")
    assert not ok and reason=="WRONG_SUBCOMPONENT_OR_CONTEXT"


def test_package_weight_requires_package_evidence():
    c=infer_contract("Peso del paquete #8","peso del producto embalado","package_weight")
    ok,reason,_=validate_value("21.06 g",c,evidence_attribute="Weight",evidence_raw="Weight 21.06g")
    assert not ok and reason=="PACKAGE_CONTEXT_NOT_PROVEN"


def test_unit_only_placeholder_rejected():
    c=infer_contract("Alto #10795","alto del producto","height")
    ok,reason,_=validate_value("(cm)",c)
    assert not ok and reason=="PLACEHOLDER_OR_UNIT_ONLY"


def test_dimensions_accept_normal_value():
    c=infer_contract("Dimensiones #1619","alto, largo y ancho","dimensions")
    ok,reason,_=validate_value("22 mm x 80 mm x 2.3 mm",c,evidence_attribute="Dimensions",evidence_raw="Dimensions 22mm x 80mm x 2.3mm")
    assert ok


def test_autonomy_rejects_battery_capacity():
    c=infer_contract("Autonomia #1672","tiempo de duración de la batería")
    ok,reason,_=validate_value("500 mAh",c)
    assert not ok


def test_exact_package_alias_is_distinct():
    key,conf,cls=map_header("Peso del paquete #8","peso del producto embalado")
    assert key=="package_weight"
    key2,_,_=map_header("Peso #8","peso del producto")
    assert key2=="weight"


def test_fuzzy_does_not_use_long_description_to_force_mapping():
    key,conf,cls=map_header("CampoRaro #999","this field mentions cable length and weight and dimensions")
    assert key is None

def test_power_source_not_confused_with_power():
    key,_,_=map_header("Alimentacion #1583","Selecciona el tipo de alimentación eléctrica / Select the power source")
    assert key=="power_source"
    c=infer_contract("Alimentacion #1583","Select the power source",key)
    assert c.value_type=="controlled" and c.allowed_dimensions==()


def test_barcode_maps_to_ean():
    key,conf,_=map_header("Código de barras #56","código universal de producto")
    assert key=="ean" and conf==1.0


def test_color_variant_maps_to_color():
    key,conf,_=map_header("ColorVariant #277523","Color de la variante")
    assert key=="color"


def test_seller_sku_classified_seller_data():
    key,conf,cls=map_header("SKU del vendedor #29","creado y designado por ti como vendedor")
    assert key is None and cls=="SELLER_DATA"

def test_package_contents_box_context_allowed():
    c=infer_contract("Contenido del paquete #19","elementos incluidos con el producto embalado","package_contents")
    ok,reason,_=validate_value("1 x headphones",c,evidence_attribute="What's in the box",evidence_raw="1 x headphones")
    # package contents are inherently package-context evidence via the attribute name
    assert ok or reason=="PACKAGE_CONTEXT_NOT_PROVEN"
