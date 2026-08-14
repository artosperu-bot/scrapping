import inspect

from product_intelligence.desktop import App as DesktopApp
from product_intelligence.workspace_desktop import App as WorkspaceApp


def test_excel_analysis_dispatches_heavy_preflight_off_tk_thread():
    source = inspect.getsource(DesktopApp.analyze_excel)
    assert "threading.Thread" in source
    assert "analyze_workbook" not in source
    assert hasattr(DesktopApp, "_analyze_excel_worker")
    assert hasattr(DesktopApp, "_apply_analysis_result")
    assert hasattr(DesktopApp, "_apply_analysis_error")


def test_workspace_sync_happens_after_async_analysis_result_not_at_dispatch():
    dispatch_source = inspect.getsource(WorkspaceApp.analyze_excel)
    apply_source = inspect.getsource(WorkspaceApp._apply_analysis_result)
    assert "_sync_workspace_products" not in dispatch_source
    assert "_sync_workspace_products" in apply_source
