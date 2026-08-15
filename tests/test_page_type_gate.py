from product_intelligence.page_type import PageSignals, classify_page_type


def test_product_jsonld_is_material():
    result = classify_page_type(PageSignals(
        url="https://example.com/products/widget-100",
        content_type="text/html",
        title="Widget 100",
        h1="Widget 100",
        schema_types=("Product",),
        product_entity_count=1,
        specification_block_count=1,
    ))
    assert result.page_type == "PRODUCT"
    assert result.material_allowed is True


def test_category_with_target_card_is_not_material():
    result = classify_page_type(PageSignals(
        url="https://example.com/headphones",
        content_type="text/html",
        title="All Headphones",
        h1="Headphones",
        schema_types=("ItemList", "BreadcrumbList"),
        product_entity_count=18,
        product_card_count=18,
    ))
    assert result.page_type == "CATEGORY"
    assert result.material_allowed is False


def test_update_page_is_not_material_even_on_official_domain():
    result = classify_page_type(PageSignals(
        url="https://brand.example/support/model-x/update",
        content_type="text/html",
        title="Software Update",
        h1="Notify Update",
        schema_types=("Article",),
        update_signal=True,
    ))
    assert result.page_type == "UPDATE"
    assert result.material_allowed is False


def test_pdf_is_document_and_material():
    result = classify_page_type(PageSignals(
        url="https://cdn.example.com/manuals/x100.pdf",
        content_type="application/pdf",
    ))
    assert result.page_type == "DOCUMENT"
    assert result.material_allowed is True


def test_unknown_page_fails_closed():
    result = classify_page_type(PageSignals(url="https://example.com/about"))
    assert result.page_type == "UNKNOWN"
    assert result.material_allowed is False
