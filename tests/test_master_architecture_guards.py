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


def test_valid_document_cannot_replace_requested_mpn_with_sibling_code():
    identity = ProductIdentity(brand="Acme", model="Widget 22", mpn="ABC-22")
    evidence = [
        ev("MPN", "ABC-22", "https://docs.example/manual.pdf"),
        ev("MPN", "ABC-26", "https://docs.example/manual.pdf"),
        ev("Weight", "200 g", "https://docs.example/manual.pdf"),
    ]
    rec = build_record_strict(identity, evidence, ["https://docs.example/manual.pdf"])
    assert all(str(e.raw_value) != "ABC-26" for e in rec.evidence)
    rejected = (rec.evidence_graph or {}).get("rejected_evidence", [])
    assert any("IDENTITY_EVIDENCE_CONFLICT:mpn" in str(row.get("reason")) for row in rejected)


def test_valid_family_document_cannot_promote_sibling_model():
    identity = ProductIdentity(brand="Acme", model="Widget 22")
    rec = build_record_strict(
        identity,
        [ev("Model", "Widget 26 Ultra", "https://docs.example/family-manual.pdf")],
        ["https://docs.example/family-manual.pdf"],
    )
    assert not rec.evidence
    rejected = (rec.evidence_graph or {}).get("rejected_evidence", [])
    assert any("IDENTITY_EVIDENCE_CONFLICT:model" in str(row.get("reason")) for row in rejected)
