from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .final_evidence_gate import evaluate_field_write
from .models import Evidence, ProductIdentity, ProductRecord
from .resolution_engine import (
    CONFLICTING_EVIDENCE,
    FOUND_CLASSIFIED,
    FOUND_DERIVED,
    FOUND_DIRECT,
    FOUND_MAPPED,
    NOT_APPLICABLE,
    analyze_resolution,
)


_VERIFIED_STATES = {FOUND_DIRECT, FOUND_DERIVED, FOUND_MAPPED, FOUND_CLASSIFIED, NOT_APPLICABLE}


@dataclass(frozen=True)
class FieldEvidenceEntry:
    field: str
    value: Any
    source_type: str
    authority: str | None
    source_url: str | None
    relationship: str | None
    scope: str | None
    confidence: float
    evidence: Evidence


@dataclass(frozen=True)
class FieldCoverageSnapshot:
    required_fields: tuple[str, ...]
    resolved_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    conflicted_fields: tuple[str, ...]
    field_states: tuple[tuple[str, str], ...]
    resolution: dict[str, Any]


class FieldEvidenceStore:
    """One logical field-evidence view shared by PDF and WEB records.

    Existing ProductRecord/Evidence remain the productive data model. This class only
    composes already-produced evidence after the final field gate, then delegates the
    semantic coverage decision to `resolution_engine.analyze_resolution`.
    """

    def __init__(self, identity: ProductIdentity, required_fields):
        self.identity = identity.model_copy(deep=True)
        self.required_fields = tuple(dict.fromkeys(str(field).strip() for field in required_fields or () if str(field).strip()))
        self._evidence: list[Evidence] = []
        self._entries: list[FieldEvidenceEntry] = []
        self._sources: list[str] = []
        self._conflicts: list[dict[str, Any]] = []

    @property
    def entries(self) -> tuple[FieldEvidenceEntry, ...]:
        return tuple(self._entries)

    def _merge_identity(self, observed: ProductIdentity) -> None:
        if observed.match_level == "CONFLICT" or observed.identifiers_conflicting:
            return
        current_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "EXACT": 4, "CONFLICT": 0}.get(self.identity.match_level, 0)
        observed_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "EXACT": 4, "CONFLICT": 0}.get(observed.match_level, 0)
        updates: dict[str, Any] = {}
        for name in ("brand", "manufacturer", "product_name", "model", "mpn", "sku", "ean", "upc", "gtin", "variant", "capacity", "color", "region"):
            current = getattr(self.identity, name, None)
            candidate = getattr(observed, name, None)
            if not current and candidate and observed_rank >= current_rank:
                updates[name] = candidate
        if observed_rank > current_rank:
            updates["match_level"] = observed.match_level
            updates["confidence"] = max(float(self.identity.confidence or 0), float(observed.confidence or 0))
        if updates:
            self.identity = self.identity.model_copy(update=updates)

    def ingest_record(self, record: ProductRecord) -> tuple[FieldEvidenceEntry, ...]:
        self._merge_identity(record.identity)
        accepted: list[FieldEvidenceEntry] = []
        for ev in record.evidence:
            decision = evaluate_field_write(record, ev.attribute, ev)
            if not decision.allowed:
                continue
            value = ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value
            entry = FieldEvidenceEntry(
                field=str(ev.attribute),
                value=value,
                source_type=str(ev.source_type or ""),
                authority=ev.authority or (record.fetch or {}).get("source_class"),
                source_url=ev.source_url,
                relationship=ev.document_relationship,
                scope=ev.document_scope,
                confidence=float(ev.confidence or 0),
                evidence=ev,
            )
            self._evidence.append(ev)
            self._entries.append(entry)
            accepted.append(entry)
        for url in record.sources:
            if url and url not in self._sources:
                self._sources.append(url)
        for conflict in record.conflicts:
            if conflict not in self._conflicts:
                self._conflicts.append(dict(conflict))
        return tuple(accepted)

    def aggregate_record(self) -> ProductRecord:
        return ProductRecord(
            identity=self.identity,
            evidence=list(self._evidence),
            sources=list(self._sources),
            conflicts=list(self._conflicts),
        )

    def snapshot(self) -> FieldCoverageSnapshot:
        record = self.aggregate_record()
        resolution = analyze_resolution(record, {"scrape_semantics": list(self.required_fields)})
        states = tuple((str(row["semantic"]), str(row["status"])) for row in resolution.get("fields", []))
        resolved = tuple(field for field, status in states if status in _VERIFIED_STATES)
        conflicted = tuple(field for field, status in states if status == CONFLICTING_EVIDENCE)
        unresolved = {field for field, _status in states if field not in resolved and field not in conflicted}
        missing = tuple(field for field in self.required_fields if field in unresolved or field not in {name for name, _ in states})
        return FieldCoverageSnapshot(
            required_fields=self.required_fields,
            resolved_fields=resolved,
            missing_fields=missing,
            conflicted_fields=conflicted,
            field_states=states,
            resolution=resolution,
        )
