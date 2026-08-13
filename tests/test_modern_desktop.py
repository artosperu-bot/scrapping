from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_modern_shell_module_exists_and_wraps_final_price_app():
    from product_intelligence import modern_desktop
    from product_intelligence.price_desktop import App as PriceApp

    assert issubclass(modern_desktop.App, PriceApp)


def test_modern_shell_has_primary_destinations():
    from product_intelligence import modern_desktop

    assert [item[0] for item in modern_desktop.NAV_ITEMS] == [
        "Inicio",
        "Productos",
        "Fuentes",
        "Atributos",
        "Multimedia",
        "Precios",
        "Ejecutar",
        "Auditoría",
    ]


def test_desktop_entrypoint_uses_modern_shell():
    text = (ROOT / "run_desktop.py").read_text(encoding="utf-8")
    assert "product_intelligence.modern_desktop import main" in text


def test_modern_shell_keeps_engine_workflows_inherited():
    from product_intelligence.modern_desktop import App

    assert "_start_price_indices" not in App.__dict__
    assert "_start_media_indices" not in App.__dict__
    assert "run" not in App.__dict__
    assert "repair_jsons" not in App.__dict__


def test_modern_shell_is_sidebar_dashboard_not_another_numbered_tab():
    source = (ROOT / "src" / "product_intelligence" / "modern_desktop.py").read_text(encoding="utf-8")
    assert "Sidebar.TFrame" in source
    assert "_build_dashboard" in source
    assert "_show_workspace" in source
    assert 'style.layout("Modern.TNotebook.Tab", [])' in source
    assert 'text="Inicio"' in source
    assert "self._nav_buttons" in source


def test_modern_shell_has_global_status_and_dashboard_state():
    source = (ROOT / "src" / "product_intelligence" / "modern_desktop.py").read_text(encoding="utf-8")
    assert "self.global_status" in source
    assert "_refresh_dashboard" in source
    assert "Productos detectados" in source
    assert "Archivo de trabajo" in source
    assert "Carpeta de salida" in source


def test_windows_build_smokes_the_actual_modern_shell_before_packaging():
    workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    assert "Smoke modern desktop shell" in workflow
    assert "from product_intelligence.modern_desktop import App" in workflow
    assert "app._active_workspace == 'dashboard'" in workflow
    assert "app._workspace_tabs" in workflow
    assert "app.destroy()" in workflow
