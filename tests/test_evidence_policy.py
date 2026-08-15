from product_intelligence.evidence_policy import decide_evidence, is_noise_attribute


def test_category_page_evidence_is_blocked():
    decision = decide_evidence(
        page_type="CATEGORY",
        identity_status="EXACT",
        source_class="manufacturer",
        extraction_method="jsonld",
        semantic="color",
        confidence=.99,
    )
    assert decision.allowed is False
    assert decision.reason == "PAGE_TYPE_NOT_MATERIAL"


def test_noise_keys_are_rejected():
    assert is_noise_attribute("currencyCode")
    assert is_noise_attribute("user_authenticated")
    assert not is_noise_attribute("battery_capacity")


def test_identity_conflict_blocks_every_material_fact():
    decision = decide_evidence(
        page_type="PRODUCT",
        identity_status="CONFLICT",
        source_class="manufacturer",
        extraction_method="jsonld",
        semantic="battery_capacity",
        confidence=.99,
    )
    assert decision.allowed is False
    assert decision.reason == "IDENTITY_CONFLICT"


def test_exact_manufacturer_jsonld_is_accepted():
    decision = decide_evidence(
        page_type="PRODUCT",
        identity_status="EXACT",
        source_class="manufacturer",
        extraction_method="jsonld",
        semantic="weight",
        confidence=.92,
    )
    assert decision.allowed is True
    assert decision.needs_corroboration is False


def test_weak_third_party_fact_fails_closed():
    decision = decide_evidence(
        page_type="PRODUCT",
        identity_status="COMPATIBLE",
        source_class="third_party",
        extraction_method="clean_dom",
        semantic="weight",
        confidence=.82,
    )
    assert decision.allowed is False
    assert decision.reason == "INSUFFICIENT_CORROBORATION"
