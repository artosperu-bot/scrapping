from product_intelligence.price_peru_coverage import _is_peru_retail_candidate


def test_peru_named_dotcom_exact_product_is_admissible_without_domain_oracle():
    assert _is_peru_retail_candidate(
        "https://retailerperu.com/product/abc123",
        "ABC/123",
    )


def test_generic_foreign_dotcom_stays_rejected():
    assert not _is_peru_retail_candidate(
        "https://retailerexample.com/product/abc123",
        "ABC/123",
    )
