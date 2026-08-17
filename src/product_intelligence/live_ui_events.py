from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ScopeKey = tuple[str, str | None, int | None, str]


@dataclass
class LiveUiScope:
    stage: str | None = None
    action: str | None = None
    source: str | None = None
    status: str | None = None
    found: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0
    percent: int | None = None
    accepted: dict[str, Any] = field(default_factory=dict)
    rejected: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class LiveUiState:
    scopes: dict[ScopeKey, LiveUiScope] = field(default_factory=dict)


def event_key(event: dict) -> ScopeKey:
    module = str(event.get("module") or "")
    workspace_id = event.get("workspace_id")
    workspace = str(workspace_id) if workspace_id is not None else None
    product_index = event.get("product_index")
    product = int(product_index) if product_index is not None else None
    run_id = str(event.get("run_id") or "")
    return (module, workspace, product, run_id)


def _non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def apply_event(state: LiveUiState, event: dict) -> LiveUiScope:
    key = event_key(event)
    scope = state.scopes.setdefault(key, LiveUiScope())

    for name in ("stage", "action", "source", "status"):
        value = event.get(name)
        if value is not None:
            setattr(scope, name, str(value))

    if event.get("found") is not None:
        scope.found = _non_negative_int(event.get("found"), scope.found)
    if event.get("accepted") is not None:
        scope.accepted_count = _non_negative_int(event.get("accepted"), scope.accepted_count)
    if event.get("rejected") is not None:
        scope.rejected_count = _non_negative_int(event.get("rejected"), scope.rejected_count)
    if event.get("percent") is not None:
        scope.percent = min(100, _non_negative_int(event.get("percent")))

    kind = str(event.get("type") or "")
    item_key = str(event.get("item_key") or "").strip()

    if kind == "accepted" and item_key:
        if item_key in scope.accepted:
            scope.duplicate_count += 1
        else:
            scope.accepted[item_key] = event.get("item")
            scope.accepted_count = max(scope.accepted_count, len(scope.accepted))

    elif kind == "rejected" and item_key:
        if item_key in scope.rejected:
            scope.duplicate_count += 1
        else:
            scope.rejected[item_key] = event.get("reason") or event.get("item")
            scope.rejected_count = max(scope.rejected_count, len(scope.rejected))

    elif kind == "duplicate":
        scope.duplicate_count += 1

    if kind == "error" or event.get("error"):
        error = str(event.get("error") or event.get("message") or "error").strip()
        if error:
            scope.errors.append(error)

    return scope
