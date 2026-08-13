from pathlib import Path


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
    text = Path("run_desktop.py").read_text(encoding="utf-8")
    assert "product_intelligence.modern_desktop import main" in text


def test_modern_shell_keeps_engine_workflows_inherited():
    from product_intelligence.modern_desktop import App

    assert "_start_price_indices" not in App.__dict__
    assert "_start_media_indices" not in App.__dict__
    assert "run" not in App.__dict__
    assert "repair_jsons" not in App.__dict__
