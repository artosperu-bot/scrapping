from product_intelligence.canonical_facts import build_canonical_facts
from product_intelligence.discovery import _rank_candidates, search_web_for_fields
from product_intelligence.evidence_quality import strict_semantic_gate
from product_intelligence.identity import sanitize_condition_mismatched_identity
from product_intelligence.media_discovery import discover_media
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord


def ev(attr, value, *, selector=None, source_type="secondary_html", confidence=.90):
    return Evidence(
        attribute=attr,
        raw_value=value,
        normalized_value=value,
        source_url="https://example.com/product",
        source_type=source_type,
        selector=selector,
        match_level="EXACT",
        confidence=confidence,
    )


def record(*evidence, **identity):
    return ProductRecord(identity=ProductIdentity(match_level="EXACT", confidence=.98, **identity), evidence=list(evidence))


def test_bluetooth_transmitter_power_does_not_create_bluetooth_transport():
    rec = record(
        ev("Bluetooth Transmitter Power", "20 dBm"),
        ev("Interface", "2.4 GHz Radio/RF"),
        mpn="GEN-RF",
    )
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["rf_2_4ghz"] is True
    assert facts["connectivity"]["bluetooth"]["present"] is not True
    assert facts["connectivity"]["bluetooth"]["version"] is None


def test_usb_c_charging_cable_does_not_become_host_connectivity():
    rec = record(
        ev("What's in the box?", "1 x USB-C charging cable; 1 x headset"),
        ev("Interface", "2.4 GHz Radio/RF"),
        mpn="GEN-RF-CHARGE",
    )
    facts = build_canonical_facts(rec)
    assert facts["connectivity"]["rf_2_4ghz"] is True
    assert facts["connectivity"]["usb_c"] is False
    assert facts["connectivity"]["wired"] is not True


def test_image_json_dimensions_are_not_physical_product_dimensions():
    width = ev("width", "1395", selector="json:product.images.width", source_type="secondary_xhr_json")
    height = ev("height", "1395", selector="json:product.images.height", source_type="secondary_xhr_json")
    assert strict_semantic_gate("width", width)[0] is False
    assert strict_semantic_gate("height", height)[0] is False


def test_refurbished_product_page_media_is_not_autofilled_for_standard_target():
    identity = ProductIdentity(mpn="JBLQ350WLBLKAM", brand="JBL")
    html = '''
    <html><body>
      <div class="product-gallery">
        <img src="/cdn/JBLQ350WLBLKAM-product-image.jpg"
             alt="JBL Quantum 350 Wireless Gaming Headset - Certified Refurbished">
      </div>
    </body></html>
    '''
    media = discover_media(
        html,
        "https://shop.example/products/jblq350wlblkam-certified-refurbished",
        identity,
        page_is_validated=True,
    )
    item = next(x for x in media if "JBLQ350WLBLKAM-product-image.jpg" in x["url"])
    assert item["autofill_eligible"] is False
    assert "condition_mismatch" in (item.get("conflict_reasons") or [])


def test_official_model_page_can_be_candidate_without_mpn_in_search_snippet():
    identity = ProductIdentity(
        mpn="JBLENDURRUN3BTBAM",
        brand="JBL",
        model="JBL Endurance Run 3 Wireless",
    )
    rows = [(
        "https://www.jbl.com/ENDURANCE-RUN-3-WIRELESS.html",
        "JBL Endurance Run 3 Wireless",
        "Sports in-ear headphones with Bluetooth",
    )]
    ranked = _rank_candidates(rows, identity, 10)
    assert len(ranked) == 1
    assert ranked[0].likely_official is True


def test_official_model_page_uses_product_name_when_model_is_only_the_mpn():
    identity = ProductIdentity(
        mpn="JBLENDURRUN3BTBAM",
        brand="JBL",
        model="JBLENDURRUN3BTBAM",
        product_name="JBL Endurance Run 3 Wireless Blue",
    )
    rows = [(
        "https://www.jbl.com/ENDURANCE-RUN-3-WIRELESS.html",
        "JBL Endurance Run 3 Wireless",
        "Sports in-ear headphones with Bluetooth",
    )]
    ranked = _rank_candidates(rows, identity, 10)
    assert len(ranked) == 1
    assert ranked[0].likely_official is True


def test_refurbished_source_does_not_replace_standard_identity_name():
    expected = ProductIdentity(mpn="JBLQ350WLBLKAM", brand="JBL")
    rec = record(
        mpn="JBLQ350WLBLKAM",
        brand="JBL",
        product_name="JBL Quantum 350 Wireless Gaming Headset - Certified Refurbished",
    )
    sanitize_condition_mismatched_identity(expected, rec.identity)
    assert rec.identity.product_name is None
    assert rec.identity.mpn == "JBLQ350WLBLKAM"


def test_release_year_gap_research_uses_release_language(monkeypatch):
    queries = []

    def fake_provider_search(query, timeout):
        queries.append(query)
        return []

    monkeypatch.setattr("product_intelligence.discovery._provider_search", fake_provider_search)
    identity = ProductIdentity(mpn="GEN-YEAR-1", brand="Example", model="Example Product")
    search_web_for_fields(identity, ["AnoFabricacion"], limit=5, timeout=1)
    joined = "\n".join(queries).lower()
    assert "release" in joined or "launch" in joined or "announcement" in joined
