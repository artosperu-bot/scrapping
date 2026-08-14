from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class TemplateProfile:
    profile_id: str
    name: str
    field_map: Mapping[str, str] = field(default_factory=dict)
    allowed_values: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)

    def map_canonical(self, canonical: Mapping[str, Any]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for canonical_field, excel_column in self.field_map.items():
            if canonical_field not in canonical:
                continue
            value = canonical[canonical_field]
            allowed = self.allowed_values.get(canonical_field)
            if allowed is not None and value not in allowed:
                continue
            output[excel_column] = value
        return output


class TemplateProfileRegistry:
    def __init__(self):
        self._profiles: dict[str, TemplateProfile] = {}

    def register(self, profile: TemplateProfile) -> None:
        if not profile.profile_id.strip():
            raise ValueError("profile_id is required")
        self._profiles[profile.profile_id] = profile

    def get(self, profile_id: str) -> TemplateProfile:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise KeyError(profile_id) from exc

    def list_profiles(self) -> list[TemplateProfile]:
        return list(self._profiles.values())
