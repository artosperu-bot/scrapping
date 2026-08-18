from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .field_evidence_store import FieldEvidenceStore
from .field_resolution_planner import plan_fields
from .models import ProductIdentity, ProductRecord
from .source_router import SourceIntent, route_sources
from .source_strategy import SourceStrategy
from .universal_resolution_policy import (
    ResolutionBudget,
    ResolutionState,
    SearchBudgetTracker,
    evaluate_next_action,
)


@dataclass(frozen=True)
class OrchestratorSnapshot:
    required_fields: tuple[str, ...]
    resolved_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    conflicted_fields: tuple[str, ...]
    source_history: tuple[dict[str, Any], ...]
    early_stop: bool
    stop_reason: str | None
    next_intents: tuple[SourceIntent, ...]


class ProductEvidenceOrchestrator:
    """Decision layer above existing PDF/WEB engines.

    This class does not fetch or extract. It owns shared field state, one search
    budget and BEST-EVIDENCE-FIRST source intents while existing engines keep their
    specialized acquisition/validation responsibilities.
    """

    def __init__(
        self,
        identity: ProductIdentity,
        required_fields,
        *,
        category: str | None = None,
        budget: ResolutionBudget | None = None,
        source_strategy: SourceStrategy | None = None,
    ):
        self.identity = identity.model_copy(deep=True)
        self.required_fields = tuple(dict.fromkeys(str(field).strip() for field in required_fields or () if str(field).strip()))
        self.category = category
        self.budget = budget or ResolutionBudget()
        self.budget_tracker = SearchBudgetTracker(self.budget)
        self.source_strategy = (source_strategy or SourceStrategy()).normalized()
        self.store = FieldEvidenceStore(self.identity, self.required_fields)
        self._source_history: list[dict[str, Any]] = []
        self._last_snapshot: OrchestratorSnapshot | None = None

    def _history_row(self, **values) -> None:
        self._source_history.append({key: value for key, value in values.items() if value not in (None, "")})

    def observe_record(
        self,
        record: ProductRecord,
        *,
        engine: str,
        source_url: str,
        status: str = "ACCEPTED",
        source_kind: str | None = None,
    ) -> OrchestratorSnapshot:
        before = set(self.store.snapshot().resolved_fields)
        accepted_entries = self.store.ingest_record(record)
        coverage = self.store.snapshot()
        added = tuple(field for field in coverage.resolved_fields if field not in before)
        effective_status = status
        if str(status).upper() == "ACCEPTED" and not accepted_entries and not added:
            effective_status = "NO_VALUE"
        if accepted_entries and self.budget_tracker.can_accept_source():
            self.budget_tracker.accept_source()
        self.identity = self.store.identity
        self._history_row(
            engine=str(engine),
            source_kind=source_kind or (record.fetch or {}).get("source_class") or str(engine),
            source_url=source_url,
            status=effective_status,
            fields_added=added,
            evidence_admitted=len(accepted_entries),
        )
        return self.plan_next()

    def observe_source_outcome(
        self,
        intent: SourceIntent | None,
        status: str,
        *,
        engine: str | None = None,
        reason: str = "",
        source_url: str | None = None,
    ) -> OrchestratorSnapshot:
        self._history_row(
            engine=engine or (intent.engine if intent else "UNKNOWN"),
            source_kind=intent.source_kind if intent else (engine or "UNKNOWN"),
            source_url=source_url,
            status=str(status).upper(),
            reason=reason,
            fields=intent.fields if intent else (),
        )
        return self.plan_next()

    def _resolution_state(self):
        coverage = self.store.snapshot()
        hard_conflicts: list[str] = list(coverage.conflicted_fields)
        if coverage.resolution.get("blocked"):
            for issue in coverage.resolution.get("cross_field_issues", []):
                code = str(issue.get("code") or "").strip()
                if code and code not in hard_conflicts:
                    hard_conflicts.append(code)
        state = ResolutionState(
            identity_status=str(self.store.identity.match_level or "LOW"),
            requested_fields=self.required_fields,
            resolved_fields=coverage.resolved_fields,
            search_queries=self.budget_tracker.queries_used,
            candidates_discovered=self.budget_tracker.candidates_admitted,
            pages_fetched=self.budget_tracker.pages_fetched,
            pdfs_analyzed=self.budget_tracker.pdfs_analyzed,
            sources_accepted=self.budget_tracker.sources_accepted,
            hard_conflicts=tuple(hard_conflicts),
        )
        return coverage, state

    def plan_next(self) -> OrchestratorSnapshot:
        coverage, state = self._resolution_state()
        decision = evaluate_next_action(state, budget=self.budget)
        intents: tuple[SourceIntent, ...] = ()
        if not decision.stop:
            fields = decision.fields or coverage.missing_fields
            plans = plan_fields(fields)
            intents = route_sources(
                self.store.identity,
                plans,
                category=self.category,
                strategy=self.source_strategy,
                history=self._source_history,
            )
        snapshot = OrchestratorSnapshot(
            required_fields=coverage.required_fields,
            resolved_fields=coverage.resolved_fields,
            missing_fields=coverage.missing_fields,
            conflicted_fields=coverage.conflicted_fields,
            source_history=tuple(dict(row) for row in self._source_history),
            early_stop=bool(decision.stop),
            stop_reason=decision.reason if decision.stop else None,
            next_intents=intents,
        )
        self._last_snapshot = snapshot
        return snapshot

    def audit(self) -> dict[str, Any]:
        snapshot = self._last_snapshot or self.plan_next()
        entries = [
            {
                "field": entry.field,
                "value": entry.value,
                "source_type": entry.source_type,
                "authority": entry.authority,
                "source_url": entry.source_url,
                "relationship": entry.relationship,
                "scope": entry.scope,
                "confidence": entry.confidence,
            }
            for entry in self.store.entries
        ]
        return {
            "identity": self.store.identity.model_dump(),
            "required_fields": list(snapshot.required_fields),
            "resolved_fields": list(snapshot.resolved_fields),
            "missing_fields": list(snapshot.missing_fields),
            "conflicted_fields": list(snapshot.conflicted_fields),
            "source_history": [dict(row) for row in snapshot.source_history],
            "next_intents": [asdict(intent) for intent in snapshot.next_intents],
            "early_stop": snapshot.early_stop,
            "stop_reason": snapshot.stop_reason,
            "budget": {
                "queries_used": self.budget_tracker.queries_used,
                "candidates_admitted": self.budget_tracker.candidates_admitted,
                "pages_fetched": self.budget_tracker.pages_fetched,
                "pdfs_analyzed": self.budget_tracker.pdfs_analyzed,
                "sources_accepted": self.budget_tracker.sources_accepted,
                "limits": asdict(self.budget),
            },
            "field_evidence": entries,
        }
