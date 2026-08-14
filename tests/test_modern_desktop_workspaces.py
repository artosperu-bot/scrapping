from product_intelligence.provider_desktop import App as ProviderApp
from product_intelligence.workspace_desktop import App as WorkspaceApp, WORKSPACE_NAV_KEY


def test_workspace_desktop_extends_validated_provider_shell():
    assert issubclass(WorkspaceApp, ProviderApp)
    assert WORKSPACE_NAV_KEY == "workspaces"
