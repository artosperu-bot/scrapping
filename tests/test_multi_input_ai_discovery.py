from product_intelligence.input_identity import parse_product_query
from product_intelligence.model_catalog import capability

def test_primary_identifier_autodetection():
    assert parse_product_query("JBLENDURRUN3BTBAM").mpn=="JBLENDURRUN3BTBAM"
    assert parse_product_query("123456789012").upc=="123456789012"
    assert parse_product_query("1234567890123").ean=="1234567890123"
    assert parse_product_query("JBL Tune 530C USB-C").product_name=="JBL Tune 530C USB-C"

def test_optional_hints_strengthen_identity():
    i=parse_product_query("JBLENDURRUN3BTBAM | brand=JBL | color=Azul")
    assert i.mpn=="JBLENDURRUN3BTBAM" and i.brand=="JBL" and i.color=="Azul"

def test_web_capability_is_provider_specific():
    assert capability("openai","gpt-5-mini-2025-08-07").web_discovery
    assert capability("openrouter","mistralai/mistral-small").web_discovery
    assert not capability("ollama","mistral").web_discovery
