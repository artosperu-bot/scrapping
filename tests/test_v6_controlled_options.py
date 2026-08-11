from product_intelligence.excel_mapper import _coerce_controlled


def test_exact_controlled_option():
    v,r=_coerce_controlled("Black","ColorVariant",["Black","Blue"])
    assert v=="Black"


def test_bluetooth_presence_maps_to_yes():
    v,r=_coerce_controlled("Bluetooth 5.3","CuentaConBluetooth",["Si","No"])
    assert v=="Si"


def test_water_ip_maps_to_yes():
    v,r=_coerce_controlled("IPX5","ResistenteAlAgua",["Si","No"])
    assert v=="Si"


def test_unknown_controlled_does_not_invent():
    v,r=_coerce_controlled("PCIe 4.0 x4 NVMe","ConectividadConexion",["USB","Bluetooth","Otro","No aplica"])
    assert v is None
