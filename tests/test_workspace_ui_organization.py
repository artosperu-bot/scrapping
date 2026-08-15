from pathlib import Path

from product_intelligence.workspace_management import delete_workspace_record
from product_intelligence.workspaces import WorkspaceRepository


def test_delete_workspace_record_cascades_only_selected_workspace(tmp_path):
    repo = WorkspaceRepository(tmp_path / 'workspaces.db')
    try:
        first = repo.create_workspace('Uno')
        second = repo.create_workspace('Dos')
        product = repo.add_product(first.id, part_number='ABC-1')
        repo.create_run(product.id)

        delete_workspace_record(repo, first.id)

        assert [w.id for w in repo.list_workspaces()] == [second.id]
        assert repo.list_products(second.id) == []
    finally:
        repo.close()


def test_organized_desktop_keeps_engine_entry_points_and_nested_views():
    source = Path('src/product_intelligence/organized_desktop.py').read_text(encoding='utf-8')
    assert 'class App(WorkspaceApp)' in source
    assert 'super()._start_media_indices' not in source
    assert 'run_media_product(' not in source
    assert 'run_price_product(' not in source
    for label in ('text="Buscar"', 'text="Galería"', 'text="Auditoría"', 'text="Ofertas"', 'text="Cobertura"'):
        assert label in source
    assert 'media_audit_tree' in source
    assert 'price_audit_tree' in source


def test_managed_desktop_exposes_safe_workspace_actions():
    source = Path('src/product_intelligence/managed_desktop.py').read_text(encoding='utf-8')
    for label in (
        'text="Abrir carpeta"',
        'text="Limpiar resultados"',
        'text="Eliminar trabajo"',
        'text="Eliminar trabajo y archivos..."',
    ):
        assert label in source

    organized = Path('src/product_intelligence/organized_desktop.py').read_text(encoding='utf-8')
    assert 'def _workspace_busy' in organized
    assert 'delete_workspace_record' in organized
    assert 'delete_workspace_files' in organized
    assert 'clean_workspace_results' in organized
    assert 'ensure_workspace_layout' in organized


def test_launcher_uses_final_managed_shell_without_removing_prior_layers():
    source = Path('run_desktop.py').read_text(encoding='utf-8')
    assert 'managed_main()' in source
    assert 'product_intelligence.workspace_desktop' in source
    assert 'product_intelligence.organized_desktop' in source
    assert 'product_intelligence.provider_desktop' in source
