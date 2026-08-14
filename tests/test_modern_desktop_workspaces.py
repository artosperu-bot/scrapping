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
