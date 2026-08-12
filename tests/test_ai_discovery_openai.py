from product_intelligence.ai_discovery import discover_official_urls
from product_intelligence.ai_enrichment import AIConfig
from product_intelligence.models import ProductIdentity


class DummyResponse:
    def raise_for_status(self):
        return None
    def json(self):
        return {
            "output_text": '{"candidates":[{"url":"https://www.jbl.com.pe/JBLENDURRUN3BTBAM.html","country":"PE","confidence":0.99,"source_kind":"specifications","reason":"exact official technical product page"}]}'
        }


def test_openai_gpt5mini_discovery_uses_web_search_and_returns_candidate(monkeypatch):
    captured={}
    def fake_post(url,headers=None,json=None,timeout=None):
        captured.update(url=url,headers=headers,json=json,timeout=timeout)
        return DummyResponse()
    monkeypatch.setattr('product_intelligence.ai_discovery.requests.post',fake_post)
    cfg=AIConfig(enabled=True,provider='openai',model='gpt-5-mini-2025-08-07',api_key='test',discovery_enabled=True,preferred_country='PE')
    result=discover_official_urls(ProductIdentity(mpn='JBLENDURRUN3BTBAM'),cfg)
    assert captured['url'].endswith('/responses')
    assert captured['json']['model']=='gpt-5-mini-2025-08-07'
    assert captured['json']['tools']==[{'type':'web_search'}]
    prompt=captured['json']['input'].lower()
    assert 'technical' in prompt
    assert 'datasheet' in prompt
    assert 'retailers' in prompt
    assert result and result[0].url.startswith('https://www.jbl.com.pe/')
    assert result[0].country=='PE'
    assert result[0].source_kind=='specifications'


def test_ai_discovery_disabled_never_calls_network(monkeypatch):
    def fail(*args,**kwargs):
        raise AssertionError('network must not be called')
    monkeypatch.setattr('product_intelligence.ai_discovery.requests.post',fail)
    cfg=AIConfig(enabled=True,provider='openai',model='gpt-5-mini-2025-08-07',discovery_enabled=False)
    assert discover_official_urls(ProductIdentity(mpn='ABC123'),cfg)==[]
