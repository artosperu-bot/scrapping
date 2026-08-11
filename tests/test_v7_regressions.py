from product_intelligence.evidence_quality import generic_evidence_gate, strict_semantic_gate
from product_intelligence.field_derivations import derive_connectivity, derive_autonomy
from product_intelligence.media_discovery import classify_media_role, validate_resource_identity
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord
from product_intelligence.record_builder import build_record_strict


def ev(attr,val,source='official_html',selector=None,conf=.95):
    return Evidence(attribute=attr,raw_value=val,normalized_value=val,source_url='https://brand.example/p',source_type=source,selector=selector,match_level='EXACT',confidence=conf)


def rec(evidence, **identity):
    i=ProductIdentity(match_level='EXACT',confidence=.98,**identity)
    return build_record_strict(i,evidence,['https://brand.example/p'])


def test_navigation_noise_rejected():
    ok,reason,_=generic_evidence_gate(ev('technical support','Why Buy Direct'))
    assert not ok


def test_subscription_noise_rejected():
    ok,reason,_=generic_evidence_gate(ev('Ingresa tu correo','Subscription Email Error'))
    assert not ok


def test_endurance_word_does_not_mean_tbw():
    e=ev('endurance_tbw','RUN 3 WIRELESS','official_pdf','line_prefix')
    ok,reason=strict_semantic_gate('endurance_tbw',e)
    assert not ok


def test_real_tbw_accepted():
    e=ev('TBW','320 TBW','official_pdf')
    ok,_=strict_semantic_gate('endurance_tbw',e)
    assert ok


def test_weight_requires_mass_unit():
    ok,_=strict_semantic_gate('weight',ev('Weight','Peso (g)'))
    assert not ok
    ok,_=strict_semantic_gate('weight',ev('Weight','21.06 g'))
    assert ok


def test_dimensions_require_vector():
    ok,_=strict_semantic_gate('dimensions',ev('Dimensions','18 mm'))
    assert not ok
    ok,_=strict_semantic_gate('dimensions',ev('Dimensions','22 mm x 80 mm x 2.3 mm'))
    assert ok


def test_power_rejects_speed_unit():
    ok,_=strict_semantic_gate('power',ev('Power','10 m/s'))
    assert not ok


def test_package_marketing_prose_rejected():
    ok,_=strict_semantic_gate('package_contents',ev('package_contents','Get even more control and personalization of your'))
    assert not ok


def test_package_explicit_contents_accepted():
    ok,_=strict_semantic_gate('package_contents',ev('Package contents','1 x Headphones, 1 x USB cable'))
    assert ok


def test_wireless_does_not_trigger_wired():
    r=rec([ev('description','Wireless sport headphones with Bluetooth 5.4')],brand='JBL',product_name='Wireless Sport Headphones',model='X')
    d=derive_connectivity(r,['Bluetooth','Alámbrico','Inalámbrico','USB-C'])
    assert 'Inalámbrico' in d.value
    assert 'Alámbrico' not in d.value


def test_autonomy_from_hour_labeled_attribute():
    r=rec([ev('Tiempo de juego máximo (horas)','25')],brand='X',model='Y')
    d=derive_autonomy(r)
    assert d.value=='25 h'


def test_feature_icon_not_gallery():
    role,ok=classify_media_role('https://brand.example/pdp/icon_battery.png','Battery life','dom:src','image')
    assert role=='page_asset' and not ok


def test_product_hero_is_gallery():
    role,ok=classify_media_role('https://brand.example/catalog/Product_Image_Hero_Black.png','Product Hero','dom:src','image')
    assert role=='product_gallery' and ok


def test_other_color_resource_rejected():
    i=ProductIdentity(brand='JBL',model='Tune 530C',color='Black')
    scope,conf,evs,conflicts=validate_resource_identity('https://x/Tune_530C_Hero_Beige.png',i,found_on_validated_product_page=True,surrounding_text='JBL Tune 530C Beige')
    assert scope=='UNVERIFIED' and 'color_conflict' in conflicts


def test_matching_color_model_is_exact_variant():
    i=ProductIdentity(brand='JBL',model='Tune 530C',color='Black')
    scope,conf,evs,conflicts=validate_resource_identity('https://x/Tune_530C_Hero_Black.png',i,found_on_validated_product_page=True,surrounding_text='JBL Tune 530C Black')
    assert scope=='EXACT_VARIANT'
