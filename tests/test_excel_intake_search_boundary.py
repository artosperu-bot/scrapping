from product_intelligence.discovery import build_query
from product_intelligence.models import ProductIdentity


def test_sku_only_fallback_produces_a_search_query():
    identity = ProductIdentity(sku="STORE-IPC-S042")
    assert build_query(identity) == '"STORE-IPC-S042"'
