from product_intelligence.ai_enrichment import AIConfig, AIEnricher
from product_intelligence.field_derivations import derive_description
from product_intelligence.models import ProductIdentity, ProductRecord, Evidence


def rec():
    return ProductRecord(
        identity=ProductIdentity(brand='JBL',product_name='JBL X',model='X',mpn='ABC',match_level='EXACT',confidence=.99),
        evidence=[
            Evidence(attribute='description',raw_value='Wireless headset.',normalized_value='Wireless headset.',source_type='official_html',source_url='https://brand.test/x',match_level='EXACT',confidence=.99),
            Evidence(attribute='Driver size',raw_value='40 mm',normalized_value='40 mm',source_type='official_pdf',source_url='https://brand.test/x.pdf',match_level='EXACT',confidence=.95),
            Evidence(attribute='Music play time',raw_value='22 hrs',normalized_value='22 hrs',source_type='official_pdf',source_url='https://brand.test/x.pdf',match_level='EXACT',confidence=.95),
        ]
    )


def test_rich_description_combines_verified_evidence():
    x=derive_description(rec())
    assert 'Wireless headset' in x.value
    assert '40 mm' in x.value
    assert '22 hrs' in x.value
    assert x.confidence >= .9


def test_ai_off_returns_none():
    ai=AIEnricher(AIConfig(enabled=False))
    assert ai.suggest(rec(),'Descripción') is None


def test_ai_rejects_numeric_hallucination(monkeypatch):
    ai=AIEnricher(AIConfig(enabled=True,provider='ollama',model='x'))
    monkeypatch.setattr(ai,'_call',lambda messages:{'value':'Autonomía 99 horas','evidence_ids':[2],'confidence':.99,'reason':'x'})
    assert ai.suggest(rec(),'Descripción') is None


def test_ai_accepts_grounded_description(monkeypatch):
    ai=AIEnricher(AIConfig(enabled=True,provider='ollama',model='x'))
    monkeypatch.setattr(ai,'_call',lambda messages:{'value':'Audífono con driver de 40 mm y autonomía de 22 hrs','evidence_ids':[1,2],'confidence':.94,'reason':'grounded'})
    ans=ai.suggest(rec(),'Descripción')
    assert ans and '40 mm' in ans['value'] and '22 hrs' in ans['value']
