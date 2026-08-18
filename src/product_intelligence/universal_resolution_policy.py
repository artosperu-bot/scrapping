from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SOURCE_TIERS = (
    "EXISTING_IDENTIFIERS",
    "IDENTITY_RESOLVER",
    "MANUFACTURER",
    "PRODUCT_CONTENT",
    "CATEGORY_PROVIDER",
    "AUTHORIZED_DISTRIBUTOR",
    "LIMITED_WEB_FALLBACK",
)

@dataclass(frozen=True)
class ResolutionBudget:
    max_search_queries_per_product: int = 8
    max_candidates_per_query: int = 5
    max_pages_fetched_per_product: int = 15
    max_pdfs_analyzed_per_product: int = 8
    max_sources_accepted_per_product: int = 5

@dataclass(frozen=True)
class SourceOutcome:
    source: str
    tier: str
    status: str
    fields_added: tuple[str, ...] = ()
    identity_status: str | None = None
    reason: str = ""

@dataclass(frozen=True)
class ResolutionState:
    identity_status: str = "INSUFFICIENT"
    requested_fields: tuple[str, ...] = ()
    resolved_fields: tuple[str, ...] = ()
    search_queries: int = 0
    candidates_discovered: int = 0
    pages_fetched: int = 0
    pdfs_analyzed: int = 0
    sources_accepted: int = 0
    current_tier: str | None = None
    hard_conflicts: tuple[str, ...] = ()

@dataclass(frozen=True)
class ResolutionDecision:
    action: str
    reason: str
    stop: bool = False
    fields: tuple[str, ...] = ()

def missing_fields(requested, resolved) -> tuple[str, ...]:
    resolved_keys = {str(value).strip().casefold() for value in resolved if str(value).strip()}
    seen: set[str] = set()
    out: list[str] = []
    for value in requested:
        text = str(value).strip()
        key = text.casefold()
        if not text or key in seen or key in resolved_keys:
            continue
        seen.add(key)
        out.append(text)
    return tuple(out)

def next_source_tier(current: str | None, *, outcome: SourceOutcome | None = None) -> str | None:
    if current is None:
        return DEFAULT_SOURCE_TIERS[0]
    try:
        index = DEFAULT_SOURCE_TIERS.index(str(current))
    except ValueError:
        return DEFAULT_SOURCE_TIERS[0]
    return DEFAULT_SOURCE_TIERS[index + 1] if index + 1 < len(DEFAULT_SOURCE_TIERS) else None

def _budget_exhausted(state: ResolutionState, budget: ResolutionBudget) -> str | None:
    checks = (
        (state.search_queries >= budget.max_search_queries_per_product, "SEARCH_QUERY_BUDGET"),
        (state.pages_fetched >= budget.max_pages_fetched_per_product, "PAGE_FETCH_BUDGET"),
        (state.pdfs_analyzed >= budget.max_pdfs_analyzed_per_product, "PDF_ANALYSIS_BUDGET"),
        (state.sources_accepted >= budget.max_sources_accepted_per_product, "SOURCE_ACCEPT_BUDGET"),
    )
    return next((reason for exhausted, reason in checks if exhausted), None)

def _search_is_too_noisy(state: ResolutionState, budget: ResolutionBudget) -> bool:
    threshold = max(20, budget.max_candidates_per_query * 4)
    return state.candidates_discovered > threshold and state.identity_status.upper() != "EXACT"

def evaluate_next_action(state: ResolutionState, *, budget: ResolutionBudget | None = None) -> ResolutionDecision:
    budget = budget or ResolutionBudget()
    identity = str(state.identity_status or "INSUFFICIENT").upper()
    gaps = missing_fields(state.requested_fields, state.resolved_fields)
    if state.hard_conflicts:
        return ResolutionDecision("MANUAL_REVIEW_REQUIRED", "UNRESOLVED_HARD_CONFLICT", True, gaps)
    if _search_is_too_noisy(state, budget):
        return ResolutionDecision("REFINE_IDENTITY", "SEARCH_TOO_NOISY", False, gaps)
    exhausted = _budget_exhausted(state, budget)
    if identity in {"AMBIGUOUS", "PARTIAL", "PARTIAL_IDENTITY", "INSUFFICIENT", "UNKNOWN", "REJECTED"}:
        if exhausted:
            return ResolutionDecision("STOP_BUDGET_EXHAUSTED", exhausted, True, gaps)
        return ResolutionDecision("REFINE_IDENTITY", "IDENTITY_NOT_SUFFICIENT", False, gaps)
    if not gaps and identity in {"EXACT", "HIGH"}:
        return ResolutionDecision("EARLY_STOP", "SUFFICIENT_FIELD_COVERAGE", True, ())
    if exhausted:
        return ResolutionDecision("STOP_BUDGET_EXHAUSTED", exhausted, True, gaps)
    if identity in {"EXACT", "HIGH"}:
        return ResolutionDecision("SEARCH_MISSING_FIELDS", "IDENTITY_SUFFICIENT_FIELDS_MISSING", False, gaps)
    return ResolutionDecision("REFINE_IDENTITY", "IDENTITY_NOT_SUFFICIENT", False, gaps)
