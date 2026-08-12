from product_intelligence.models import ProductRecord, ProductIdentity, Evidence
from product_intelligence.field_derivations import derive_connectivity
from product_intelligence.target_extract import extract_target_evidence


def test_target_extract_supports_never_seen_excel_semantic():
    text="Velocidad máxima: 320 km/h\nOtro dato: X"
    ev=extract_target_evidence(text,["VelocidadMaxima"],"https://example.test/p","official_html","EXACT",.95)
    assert ev and ev[0].attribute=="VelocidadMaxima" and "320" in str(ev[0].raw_value)


def test_connectivity_does_not_treat_charging_usb_as_audio_connectivity():
    rec=ProductRecord(identity=ProductIdentity(product_name="Wireless headset",match_level="EXACT"),evidence=[
        Evidence(attribute="Charging Input",raw_value="USB-C",normalized_value="USB-C",source_url="x",source_type="official_html",match_level="EXACT",confidence=.98),
        Evidence(attribute="Wireless",raw_value="2.4 GHz Radio/RF",normalized_value="2.4 GHz Radio/RF",source_url="x",source_type="official_html",match_level="EXACT",confidence=.98),
    ])
    d=derive_connectivity(rec,["USB-C","Inalámbrico","Radiofrecuencia (RF)"])
    assert "USB-C" not in str(d.value)
    assert "Inalámbrico" in str(d.value)


def test_connectivity_keeps_usb_c_when_audio_connector_proves_it():
    rec=ProductRecord(identity=ProductIdentity(product_name="Wired headset",match_level="EXACT"),evidence=[
        Evidence(attribute="Audio Connector",raw_value="1x USB-C",normalized_value="1x USB-C",source_url="x",source_type="official_html",match_level="EXACT",confidence=.98),
    ])
    d=derive_connectivity(rec,["USB-C","Inalámbrico"])
    assert d.value=="USB-C"
