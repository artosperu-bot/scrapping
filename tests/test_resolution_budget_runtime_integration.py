from product_intelligence import discovery
from product_intelligence.models import ProductIdentity
from product_intelligence.universal_resolution_policy import ResolutionBudget, SearchBudgetTracker


def _identity():
    return ProductIdentity(brand="Example", model="Model X Wireless", mpn="EXM-X-100")


def test_search_budget_tracker_never_reserves_more_than_global_query_limit():
    tracker = SearchBudgetTracker(ResolutionBudget(max_search_queries_per_product=3))
    assert tracker.reserve_query() is True
    assert tracker.reserve_query() is True
    assert tracker.reserve_query() is True
    assert tracker.reserve_query() is False
    assert tracker.queries_used == 3


def test_search_web_respects_per_call_quota_and_shared_global_budget(monkeypatch):
    queries = []

    def fake_provider_search(query, timeout):
        queries.append(query)
        return []

    monkeypatch.setattr(discovery, "_provider_search", fake_provider_search)
    tracker = SearchBudgetTracker(ResolutionBudget(max_search_queries_per_product=5))

    discovery.search_web(_identity(), limit=20, budget_tracker=tracker, query_quota=3)
    assert tracker.queries_used == 3
    assert len(queries) == 3

    discovery.search_web_for_fields(
        _identity(),
        ["weight", "battery", "color"],
        limit=20,
        budget_tracker=tracker,
        query_quota=3,
    )
    assert tracker.queries_used == 5
    assert len(queries) == 5


def test_each_search_query_contributes_at_most_configured_candidate_budget(monkeypatch):
    rows = [
        (f"https://example.com/product-{index}", f"Example Model X Wireless EXM-X-100 result {index}", "specifications")
        for index in range(20)
    ]
    monkeypatch.setattr(discovery, "_provider_search", lambda query, timeout: list(rows))
    tracker = SearchBudgetTracker(
        ResolutionBudget(max_search_queries_per_product=2, max_candidates_per_query=5)
    )

    result = discovery.search_web(
        _identity(),
        limit=20,
        budget_tracker=tracker,
        query_quota=1,
    )
    assert tracker.queries_used == 1
    assert len(result) <= 5


def test_batch_source_cap_is_driven_by_resolution_budget():
    from product_intelligence import batch

    assert batch.MAX_VALIDATED_SOURCES_PER_PRODUCT == ResolutionBudget().max_sources_accepted_per_product
    assert batch.MAX_VALIDATED_SOURCES_PER_PRODUCT == 5


def test_batch_query_stage_quotas_reserve_budget_for_refinement_and_gaps():
    from product_intelligence import batch

    quotas = batch.SEARCH_STAGE_QUERY_QUOTAS
    assert quotas["INITIAL"] + quotas["IDENTITY_REFINEMENT"] + quotas["MISSING_FIELDS"] <= ResolutionBudget().max_search_queries_per_product
    assert quotas["INITIAL"] >= 1
    assert quotas["IDENTITY_REFINEMENT"] >= 1
    assert quotas["MISSING_FIELDS"] >= 1
