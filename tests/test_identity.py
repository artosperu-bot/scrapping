from product_intelligence.models import ProductIdentity
from product_intelligence.identity import compare_identity, detect_identifier

def test_identifier_detection():
    assert detect_identifier("1234567890123") == "ean"
    assert detect_identifier("SA400S37/960G") == "mpn_or_model"

def test_strong_conflict():
    a=ProductIdentity(mpn="ABC-1")
    b=ProductIdentity(mpn="XYZ-2")
    assert compare_identity(a,b).match_level == "CONFLICT"

def test_exact_mpn():
    a=ProductIdentity(mpn="SA400S37/960G")
    b=ProductIdentity(mpn="SA400S37/960G")
    assert compare_identity(a,b).match_level == "EXACT"
