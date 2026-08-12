from product_intelligence.evidence_quality import strict_semantic_gate
from product_intelligence.identity import compare_identity
from product_intelligence.models import Evidence, ProductIdentity
from product_intelligence.record_builder import build_record_strict


def ev(attribute, value, source="https://shop.example/product"):
    return Evidence(
        attribute=attribute,
        raw_value=value,
        normalized_value=value,
        source_url=source,
        source_type="secondary_html",
        match_level="EXACT",
        confidence=.82,
    )


def test_seller_organization_does_not_become_brand_from_mpn_alone():
    expected=ProductIdentity(mpn="ABC123")
    candidate=ProductIdentity(mpn="ABC123", brand="Example Commerce SAC", product_name="Acme Widget ABC123")
    result=compare_identity(expected,candidate)
    assert result.match_level == "EXACT"
    assert result.brand is None
    assert result.confidence < .90


def test_explicit_product_brand_repairs_merchant_identity():
    identity=ProductIdentity(mpn="ABC123", brand="Example Commerce SAC", product_name="Acme Widget ABC123", match_level="EXACT", confidence=.32)
    rec=build_record_strict(identity,[ev("Brand","Acme")],["https://shop.example/product"])
    assert rec.identity.brand == "Acme"


def test_label_shaped_values_are_rejected_before_resolution():
    cases=[
        ("processor", ev("Processor","de PC")),
        ("bluetooth", ev("Bluetooth version","Versión Bluetooth")),
        ("color", ev("Color","del dial")),
        ("interface", ev("Interface","de Audio")),
    ]
    for canonical,evidence in cases:
        ok,_=strict_semantic_gate(canonical,evidence)
        assert not ok


def test_duplicate_evidence_is_one_vote():
    evidence=[
        ev("Color","Black"),
        ev("Color","Black"),
        ev("Color","Black"),
    ]
    rec=build_record_strict(ProductIdentity(mpn="ABC123"),evidence,["https://shop.example/product"])
    assert not rec.conflicts
    assert len(rec.evidence) == 1
    assert "evidence_deduplicated:2" in rec.warnings
