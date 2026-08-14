from product_intelligence.modern_desktop import NAV_ITEMS, _PAGE_COPY


def test_modern_desktop_registers_persistent_workspaces_navigation():
    keys = [key for _label, key in NAV_ITEMS]

    assert "workspaces" in keys
    assert _PAGE_COPY["workspaces"][0] == "Trabajos"
