from product_intelligence.live_ui_events import LiveUiState, apply_event, event_key


def _base(**extra):
    event = {
        "module": "price",
        "workspace_id": "ws-a",
        "product_index": 0,
        "run_id": "run-1",
    }
    event.update(extra)
    return event


def test_event_key_isolates_workspace_product_module_and_run():
    assert event_key(_base()) == ("price", "ws-a", 0, "run-1")
    assert event_key(_base(workspace_id="ws-b")) != event_key(_base())
    assert event_key(_base(product_index=1)) != event_key(_base())
    assert event_key(_base(module="pdf")) != event_key(_base())
    assert event_key(_base(run_id="run-2")) != event_key(_base())


def test_apply_event_dedupes_accepted_items_and_keeps_duplicate_observable():
    state = LiveUiState()
    accepted = _base(type="accepted", item_key="https://store.test/p/1", item={"url": "https://store.test/p/1"})
    apply_event(state, accepted)
    apply_event(state, accepted)

    scope = state.scopes[event_key(accepted)]
    assert list(scope.accepted) == ["https://store.test/p/1"]
    assert scope.accepted_count == 1
    assert scope.duplicate_count == 1


def test_apply_event_tracks_rejected_error_and_real_counters_without_inventing_percentage():
    state = LiveUiState()
    apply_event(state, _base(type="status", stage="SEARCH", found=12, accepted=2, rejected=3))
    apply_event(state, _base(type="rejected", item_key="bad-1", reason="IDENTITY_MISMATCH"))
    apply_event(state, _base(type="error", error="HTTP 403"))

    scope = state.scopes[event_key(_base())]
    assert scope.stage == "SEARCH"
    assert scope.found == 12
    assert scope.accepted_count == 2
    assert scope.rejected_count >= 3
    assert scope.errors[-1] == "HTTP 403"
    assert scope.percent is None


def test_apply_event_does_not_cross_contaminate_products_or_workspaces():
    state = LiveUiState()
    a = _base(type="accepted", item_key="a", item={"value": "A"})
    b = _base(workspace_id="ws-b", product_index=2, type="accepted", item_key="b", item={"value": "B"})
    apply_event(state, a)
    apply_event(state, b)

    assert list(state.scopes[event_key(a)].accepted) == ["a"]
    assert list(state.scopes[event_key(b)].accepted) == ["b"]
    assert event_key(a) != event_key(b)
