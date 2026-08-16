from product_intelligence.source_authority import AuthoritySignals, classify_source_authority


def test_brand_token_in_hostname_is_not_manufacturer_by_itself():
    result = classify_source_authority(AuthoritySignals(
        url="https://brandfixpros.example/product/abc",
        requested_brand="Brand",
    ))
    assert result.source_class != "manufacturer"


def test_consistent_brand_owned_organization_signals_can_be_manufacturer():
    result = classify_source_authority(AuthoritySignals(
        url="https://www.brand.example/products/abc",
        requested_brand="Brand",
        organization_names=("Brand",),
        canonical_host="www.brand.example",
        same_origin_product_links=12,
        brand_owned_footer=True,
    ))
    assert result.source_class == "manufacturer"


def test_marketplace_signal_wins_over_brand_text():
    result = classify_source_authority(AuthoritySignals(
        url="https://market.example/brand-x100",
        requested_brand="Brand",
        marketplace_signal=True,
    ))
    assert result.source_class == "marketplace"
