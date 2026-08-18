from product_intelligence.universal_resolution_policy import (
    DEFAULT_SOURCE_TIERS,
    ResolutionBudget,
    ResolutionState,
    SourceOutcome,
    evaluate_next_action,
    missing_fields,
    next_source_tier,
)


def test_default_budget_is_bounded_not_massive():
    budget = ResolutionBudget()
    assert budget.max_search_queries_per_product == 8
    assert budget.max_candidates_per_query == 5
    assert budget.max_pages_fetched_per_product == 15
    assert budget.max_pdfs_analyzed_per_product == 8
    assert budget.max_sources_accepted_per_product == 5


def test_source_tiers_end_with_limited_web_fallback():
    assert DEFAULT_SOURCE_TIERS[0] == "EXISTING_IDENTIFIERS"
    assert "MANUFACTURER" in DEFAULT_SOURCE_TIERS
    assert DEFAULT_SOURCE_TIERS[-1] == "LIMITED_WEB_FALLBACK"


def test_partial_identity_refines_identity_before_spec_search():
    state = ResolutionState(identity_status="AMBIGUOUS", requested_fields=("weight", "battery"))
    decision = evaluate_next_action(state)
    assert decision.action == "REFINE_IDENTITY"
    assert decision.stop is False


def test_exact_identity_and_full_coverage_early_stops():
    state = ResolutionState(
        identity_status="EXACT",
        requested_fields=("weight", "battery"),
        resolved_fields=("weight", "battery"),
    )
    decision = evaluate_next_action(state)
    assert decision.action == "EARLY_STOP"
    assert decision.stop is True
    assert decision.reason == "SUFFICIENT_FIELD_COVERAGE"


def test_missing_field_routing_only_returns_unresolved_fields():
    assert missing_fields(("weight", "height", "battery"), ("height",)) == ("weight", "battery")


def test_blocked_source_moves_to_next_tier_without_retrying_same_source():
    current = "MANUFACTURER"
    outcome = SourceOutcome(source="official_site", tier=current, status="SOURCE_BLOCKED")
    assert next_source_tier(current, outcome=outcome) == "PRODUCT_CONTENT"


def test_noisy_search_routes_back_to_identity_not_more_volume():
    state = ResolutionState(
        identity_status="HIGH",
        requested_fields=("weight",),
        candidates_discovered=26,
        search_queries=3,
    )
    decision = evaluate_next_action(state)
    assert decision.action == "REFINE_IDENTITY"
    assert decision.reason == "SEARCH_TOO_NOISY"


def test_budget_exhaustion_fails_closed_instead_of_searching_more():
    budget = ResolutionBudget(max_pages_fetched_per_product=4)
    state = ResolutionState(
        identity_status="EXACT",
        requested_fields=("weight", "battery"),
        resolved_fields=("weight",),
        pages_fetched=4,
    )
    decision = evaluate_next_action(state, budget=budget)
    assert decision.action == "STOP_BUDGET_EXHAUSTED"
    assert decision.stop is True


def test_exact_identity_with_missing_fields_continues_only_for_gaps():
    state = ResolutionState(
        identity_status="EXACT",
        requested_fields=("weight", "battery", "color"),
        resolved_fields=("weight",),
    )
    decision = evaluate_next_action(state)
    assert decision.action == "SEARCH_MISSING_FIELDS"
    assert decision.fields == ("battery", "color")
