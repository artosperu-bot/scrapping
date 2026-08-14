from product_intelligence.template_profiles import TemplateProfile, TemplateProfileRegistry


def test_profile_maps_canonical_without_mutating_input():
    canonical = {"bluetooth": True, "weight_g": 252, "gtin": "6925281986505"}
    profile = TemplateProfile(
        profile_id="falabella",
        name="Falabella",
        field_map={"bluetooth": "Bluetooth", "weight_g": "Peso", "gtin": "EAN"},
    )

    result = profile.map_canonical(canonical)

    assert result == {"Bluetooth": True, "Peso": 252, "EAN": "6925281986505"}
    assert canonical == {"bluetooth": True, "weight_g": 252, "gtin": "6925281986505"}


def test_profile_registry_returns_registered_profile():
    registry = TemplateProfileRegistry()
    profile = TemplateProfile(profile_id="ripley", name="Ripley", field_map={"gtin": "GTIN"})
    registry.register(profile)

    assert registry.get("ripley") is profile
    assert registry.list_profiles() == [profile]
