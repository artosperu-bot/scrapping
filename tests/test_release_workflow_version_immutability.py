from pathlib import Path


def test_release_workflow_never_clobbers_assets_for_an_existing_version():
    workflow = Path('.github/workflows/release-windows.yml').read_text(encoding='utf-8')
    assert 'gh release upload $tag' not in workflow or '--clobber' not in workflow
    assert 'VERSION_ALREADY_RELEASED_FOR_DIFFERENT_COMMIT' in workflow
    assert 'git rev-list -n 1 $tag' in workflow
