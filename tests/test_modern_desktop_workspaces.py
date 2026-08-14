import inspect

from product_intelligence.provider_desktop import App as ProviderApp
from product_intelligence.workspace_desktop import App as WorkspaceApp, WORKSPACE_NAV_KEY


def test_workspace_desktop_extends_validated_provider_shell():
    assert issubclass(WorkspaceApp, ProviderApp)
    assert WORKSPACE_NAV_KEY == "workspaces"


def test_workspace_nav_button_uses_same_parent_as_existing_navigation():
    source = inspect.getsource(WorkspaceApp._install_workspace_page)
    assert 'nav_parent = self._nav_buttons["products"].master' in source
    assert 'ttk.Button(\n            nav_parent,' in source


def test_core_terminal_watch_is_armed_before_workspace_worker_can_emit():
    run_source = inspect.getsource(WorkspaceApp.run)
    workspace_branch = run_source.split("self._workspace_core_success = None", 1)[1]
    emit_source = inspect.getsource(WorkspaceApp.emit)
    assert workspace_branch.index("self._workspace_core_watching = True") < workspace_branch.index("super().run()")
    assert "if self._workspace_core_watching:" in emit_source
