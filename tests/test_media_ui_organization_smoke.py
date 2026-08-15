from pathlib import Path


def test_media_ui_organization_keeps_media_engine_isolated():
    source = Path('src/product_intelligence/organized_desktop.py').read_text(encoding='utf-8')
    engine = Path('src/product_intelligence/media_workflow.py').read_text(encoding='utf-8')
    assert 'self.media_views.add(search_tab, text="Buscar")' in source
    assert 'self.media_views.add(gallery_tab, text="Galería")' in source
    assert 'self.media_views.add(audit_tab, text="Auditoría")' in source
    assert 'def run_media_product(' in engine
    assert 'run_media_product(' not in source
