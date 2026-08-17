from pathlib import Path

from product_intelligence.models import ProductIdentity
from product_intelligence import document_discovery as discovery


def _identity() -> ProductIdentity:
    return ProductIdentity(
        brand="ExampleBrand",
        model="Alpha 350 Wireless",
        mpn="EXAMPLE-350-BLK",
    )


def _effective_queries() -> list[str]:
    tiers = discovery.build_document_query_tiers(_identity(), official_domain="example.com")
    return [query for tier in tiers for query in tier][: discovery.MAX_QUERY_ATTEMPTS]


def test_runtime_pdf_budget_covers_all_high_value_discovery_intents():
    queries = _effective_queries()
    joined = "\n".join(queries).lower()

    assert any('site:example.com' in q.lower() and '"example-350-blk"' in q.lower() and 'filetype:pdf' in q.lower() for q in queries)
    assert any('"example-350-blk"' in q.lower() and 'filetype:pdf' in q.lower() for q in queries)
    assert "spec" in joined or "specifications" in joined
    assert "datasheet" in joined or "data sheet" in joined
    assert "manual" in joined
    assert "support" in joined or "download" in joined


def test_runtime_pdf_budget_is_not_wasted_on_redundant_plain_pdf_variants():
    queries = _effective_queries()
    normalized = [" ".join(query.lower().replace('"', '').split()) for query in queries]

    # A scarce runtime budget should not spend separate slots on `MPN pdf` and `"MPN" pdf`.
    assert not (
        "example-350-blk pdf" in normalized
        and sum(value == "example-350-blk pdf" for value in normalized) > 1
    )


def test_review_discovery_source_is_pdf_only_before_user_confirmation():
    source = Path("src/product_intelligence/live_pdf_discovery.py").read_text(encoding="utf-8").lower()

    assert "without ocr/mistral" in source
    assert "run_ocr" not in source
    assert "mistral" not in source.replace("without ocr/mistral", "")
