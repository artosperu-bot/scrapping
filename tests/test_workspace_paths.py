from pathlib import Path

from product_intelligence.workspace_paths import (
    clean_workspace_results,
    delete_workspace_files,
    ensure_workspace_layout,
    sanitize_workspace_name,
    workspace_dir,
)


def test_sanitize_workspace_name_is_windows_safe():
    assert sanitize_workspace_name('Trabajo: JBL / agosto? *') == 'Trabajo_ JBL _ agosto'
    assert sanitize_workspace_name('CON') == 'CON_Trabajo'


def test_workspace_dir_uses_id_suffix_to_avoid_same_name_collisions(tmp_path):
    a = workspace_dir(tmp_path, 'aaaaaaaa-1111', 'Carga')
    b = workspace_dir(tmp_path, 'bbbbbbbb-2222', 'Carga')
    assert a != b
    assert a.name.startswith('Carga__')


def test_ensure_workspace_layout_creates_expected_buckets(tmp_path):
    layout = ensure_workspace_layout(tmp_path, 'abc12345-rest', 'Trabajo Uno')
    assert layout['root'].is_dir()
    for name in ('Excel', 'Scraping', 'PDF', 'multimedia', 'prices', 'Logs'):
        assert layout[name].is_dir()


def test_clean_results_preserves_excel_folder_and_removes_generated_content(tmp_path):
    layout = ensure_workspace_layout(tmp_path, 'abc12345', 'Trabajo Uno')
    original = layout['Excel'] / 'entrada.xlsx'
    original.write_bytes(b'excel')
    (layout['root'] / 'resultado.xlsx').write_bytes(b'generated')
    (layout['root'] / 'resumen.json').write_text('{}', encoding='utf-8')
    for name in ('Scraping', 'PDF', 'multimedia', 'prices', 'Logs'):
        (layout[name] / 'result.txt').write_text('x', encoding='utf-8')

    clean_workspace_results(layout['root'])

    assert original.read_bytes() == b'excel'
    assert not (layout['root'] / 'resultado.xlsx').exists()
    assert not (layout['root'] / 'resumen.json').exists()
    for name in ('Scraping', 'PDF', 'multimedia', 'prices', 'Logs'):
        assert list((layout['root'] / name).iterdir()) == []


def test_delete_workspace_files_removes_only_target_tree(tmp_path):
    layout = ensure_workspace_layout(tmp_path, 'abc12345', 'Trabajo Uno')
    sibling = Path(tmp_path) / 'keep.txt'
    sibling.write_text('keep', encoding='utf-8')

    delete_workspace_files(layout['root'])

    assert not layout['root'].exists()
    assert sibling.exists()
