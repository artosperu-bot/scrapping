def test_media_fetch_strategy_contract():
    from pathlib import Path
    text = Path('src/product_intelligence/media_workflow.py').read_text(encoding='utf-8')
    assert 'prefer_browser=True' not in text
