from product_intelligence.batch import manual_identity_items
from product_intelligence.models import ProductIdentity


def test_manual_urls_stay_bound_to_their_product(monkeypatch):
    monkeypatch.setattr(
        "product_intelligence.batch._best_product_sheet",
        lambda _template: ("Productos", 4),
    )

    identities = [
        ProductIdentity(mpn="PRODUCT-A"),
        ProductIdentity(mpn="PRODUCT-B"),
        ProductIdentity(mpn="PRODUCT-C"),
    ]
    urls = [
        ["https://maker.test/product-a", "https://support.test/product-a"],
        ["https://maker.test/product-b"],
        [],
    ]

    items = manual_identity_items("template.xlsx", identities, urls)

    assert [item.identity.mpn for item in items] == ["PRODUCT-A", "PRODUCT-B", "PRODUCT-C"]
    assert items[0].source_urls == urls[0]
    assert items[1].source_urls == urls[1]
    assert items[2].source_urls == []
    assert "https://maker.test/product-b" not in items[0].source_urls
    assert "https://maker.test/product-a" not in items[1].source_urls


def test_manual_url_lists_are_deduplicated_per_product(monkeypatch):
    monkeypatch.setattr(
        "product_intelligence.batch._best_product_sheet",
        lambda _template: ("Productos", 4),
    )
    identities = [ProductIdentity(mpn="PRODUCT-A"), ProductIdentity(mpn="PRODUCT-B")]
    urls = [
        ["https://maker.test/a", "https://maker.test/a"],
        ["https://maker.test/a"],
    ]

    items = manual_identity_items("template.xlsx", identities, urls)

    # Deduplication happens inside each product only. The same URL may be independently
    # supplied for another product, where identity validation will decide whether it is valid.
    assert items[0].source_urls == ["https://maker.test/a"]
    assert items[1].source_urls == ["https://maker.test/a"]
