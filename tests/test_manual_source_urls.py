from pathlib import Path

from product_intelligence.batch import manual_identity_items
from product_intelligence.input_identity import parse_product_entry, parse_product_entries
from product_intelligence.models import ProductIdentity


def template_path():
    return Path(__file__).resolve().parents[1] / "examples" / "ProductCreationTemplate_reference.xlsx"


def test_product_line_accepts_multiple_source_urls():
    entry = parse_product_entry(
        "JBLENDURRUN3BTBAM | brand=JBL | "
        "url=https://www.jbl.com.pe/JBLENDURRUN3BTBAM.html | "
        "url=https://support.jbl.com/example"
    )
    assert entry is not None
    assert entry.identity.mpn == "JBLENDURRUN3BTBAM"
    assert entry.identity.brand == "JBL"
    assert entry.source_urls == [
        "https://www.jbl.com.pe/JBLENDURRUN3BTBAM.html",
        "https://support.jbl.com/example",
    ]


def test_url_only_is_not_enough_to_bind_excel_row():
    assert parse_product_entry("https://example.com/product") is None


def test_manual_urls_are_bound_to_the_matching_product_row():
    identities = [ProductIdentity(mpn="ABC123"), ProductIdentity(mpn="XYZ999")]
    urls = [["https://maker.example/ABC123"], ["https://maker.example/XYZ999"]]
    items = manual_identity_items(str(template_path()), identities, urls)
    assert len(items) == 2
    assert items[0].identity.mpn == "ABC123"
    assert items[0].source_urls == ["https://maker.example/ABC123"]
    assert items[1].identity.mpn == "XYZ999"
    assert items[1].source_urls == ["https://maker.example/XYZ999"]


def test_duplicate_product_lines_are_deduplicated_even_with_sources():
    entries = parse_product_entries(
        "ABC123 | url=https://maker.example/a\n"
        "ABC123 | url=https://maker.example/b\n"
    )
    assert len(entries) == 1
