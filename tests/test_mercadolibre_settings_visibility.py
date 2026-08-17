from pathlib import Path


def test_mercadolibre_box_is_inserted_before_provider_sections():
    source = Path("src/product_intelligence/mercadolibre_desktop.py").read_text(encoding="utf-8")
    assert "existing_children = list(self.settings_tab.winfo_children())" in source
    assert "before=existing_children[1]" in source
    assert "Guardar configuración" in source
    assert "Probar conexión" in source
    assert "Renovar token ahora" in source
