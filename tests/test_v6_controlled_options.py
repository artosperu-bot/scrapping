from product_intelligence.excel_mapper_v8 import _coerce_controlled


def test_exact_controlled_option():
    value,reason=_coerce_controlled("Black","ColorVariant",["Black","Blue"])
    assert value=="Black"


def test_spanish_yes_option_maps_exactly():
    value,reason=_coerce_controlled("Sí","CuentaConBluetooth",["Sí","No"])
    assert value=="Sí"


def test_water_boolean_option_maps_exactly():
    value,reason=_coerce_controlled("Sí","ResistenteAlAgua",["Sí","No"])
    assert value=="Sí"


def test_unknown_controlled_does_not_invent():
    value,reason=_coerce_controlled("PCIe 4.0 x4 NVMe","ConectividadConexion",["USB","Bluetooth","Otro","No aplica"])
    assert value is None
