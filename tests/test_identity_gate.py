from product_intelligence.identity_gate import ObservedIdentity, assess_identity
from product_intelligence.models import ProductIdentity


def test_exact_mpn_match_passes():
    result = assess_identity(
        ProductIdentity(brand="Brand", model="Model 22", mpn="ABC-22"),
        ObservedIdentity(brand="Brand", model="Model 22", mpns=("ABC-22",)),
    )
    assert result.status == "EXACT"


def test_different_dominant_model_blocks_even_same_brand():
    result = assess_identity(
        ProductIdentity(brand="Brand", model="Model 22"),
        ObservedIdentity(brand="Brand", model="Model 26 Ultra"),
    )
    assert result.status == "CONFLICT"


def test_conflicting_strong_identifier_blocks():
    result = assess_identity(
        ProductIdentity(mpn="ABC-22"),
        ObservedIdentity(mpns=("ABC-26",)),
    )
    assert result.status == "CONFLICT"


def test_same_brand_exact_model_is_compatible_without_strong_id():
    result = assess_identity(
        ProductIdentity(brand="Brand", model="X100"),
        ObservedIdentity(brand="Brand", model="X100"),
    )
    assert result.status == "COMPATIBLE"


def test_brand_match_alone_is_not_enough():
    result = assess_identity(
        ProductIdentity(brand="Brand", model="X100"),
        ObservedIdentity(brand="Brand"),
    )
    assert result.status in {"AMBIGUOUS", "INSUFFICIENT"}
