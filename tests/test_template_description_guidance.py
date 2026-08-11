
from product_intelligence.models import ProductIdentity, ProductRecord, Evidence
from product_intelligence.field_derivations import derive_boolean, derive_description
from product_intelligence.semantic_guard import infer_contract
def rec(*ev):return ProductRecord(identity=ProductIdentity(mpn='TEST',match_level='EXACT'),evidence=list(ev))
def e(a,v):return Evidence(attribute=a,raw_value=v,normalized_value=v,source_url='https://example.test/p',source_type='manufacturer_html',match_level='EXACT',confidence=.95)
def test_description_can_define_boolean_contract():
    c=infer_contract('OpaqueField','Selecciona si el producto cuenta con bluetooth. // Select whether the product has Bluetooth. - Syntax: One value from the list',None,'UNKNOWN');assert c.semantic=='bluetooth' and c.value_type=='controlled'
def test_bluetooth_yes_from_specific_technology_evidence():assert derive_boolean(rec(e('Bluetooth Version','5.4')),'bluetooth').value=='Sí'
def test_bluetooth_no_from_closed_wired_connectivity():assert derive_boolean(rec(e('Connectivity','1x USB-C'),e('Wired Audio Connector','1x USB-C')),'bluetooth').value=='No'
def test_bluetooth_no_from_closed_24ghz_rf_connectivity():assert derive_boolean(rec(e('Connectivity','2.4 GHz Radio/RF')),'bluetooth').value=='No'
def test_spanish_description_uses_translated_fact_labels():
    r=rec(e('description','Enjoy wireless listening with powerful sound.'),e('Frequency Response','20 Hz to 20 kHz'),e('Impedance','32 Ohms'));r.identity.product_name='Test Headphones';d=derive_description(r);assert 'Respuesta de frecuencia' in d.value and 'Impedancia' in d.value
