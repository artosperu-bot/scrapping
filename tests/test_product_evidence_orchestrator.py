from product_intelligence.field_resolution_planner import plan_field
from product_intelligence.models import Evidence, ProductIdentity, ProductRecord
from product_intelligence.product_evidence_orchestrator import ProductEvidenceOrchestrator
from product_intelligence.source_router import route_sources
from product_intelligence.universal_resolution_policy import ResolutionBudget


def _identity(**updates):
    base = dict(
        brand="Example",
        model="Example Model Wireless",
        mpn="EX-100-WL",
        confidence=.99,
        match_level="EXACT",
        identifiers_confirmed=["mpn"],
    )
    base.update(updates)
    return ProductIdentity(**base)


def _evidence(
    attribute,
    value,
    *,
    source_type="official_pdf",
    authority="manufacturer",
    relationship="EXACT_MODEL",
    scope="MODEL",
    policy_allowed=True,
):
    return Evidence(
        attribute=attribute,
        raw_value=value,
        normalized_value=value,
        source_url=f"https://example.test/{attribute}",
        source_type=source_type,
        extraction_method="pdf_native" if "pdf" in source_type else "jsonld",
        match_level="EXACT",
        confidence=.96,
        identity_status="EXACT",
        authority=authority,
        policy_allowed=policy_allowed,
        document_relationship=relationship,
        document_scope=scope,
    )


def _record(*evidence, identity=None, conflicts=None):
    return ProductRecord(
        identity=identity or _identity(),
        evidence=list(evidence),
        sources=list(dict.fromkeys(ev.source_url for ev in evidence if ev.source_url)),
        conflicts=list(conflicts or []),
        fetch={"source_class": "manufacturer"},
    )


def test_pdf_resolves_all_important_fields_and_stops_before_web():
    orchestrator = ProductEvidenceOrchestrator(_identity(), ["battery_capacity"])
    snapshot = orchestrator.observe_record(
        _record(_evidence("battery_capacity", "5000 mAh")),
        engine="PDF",
        source_url="https://example.test/spec.pdf",
    )

    assert snapshot.resolved_fields == ("battery_capacity",)
    assert snapshot.missing_fields == ()
    assert snapshot.early_stop is True
    assert snapshot.stop_reason == "SUFFICIENT_FIELD_COVERAGE"
    assert not any(intent.engine.startswith("WEB") for intent in snapshot.next_intents)


def test_pdf_partial_passes_only_missing_fields_to_next_source():
    orchestrator = ProductEvidenceOrchestrator(_identity(), ["battery_capacity", "gtin"])
    snapshot = orchestrator.observe_record(
        _record(_evidence("battery_capacity", "5000 mAh")),
        engine="PDF",
        source_url="https://example.test/spec.pdf",
    )
    next_snapshot = orchestrator.plan_next()

    assert snapshot.resolved_fields == ("battery_capacity",)
    assert snapshot.missing_fields == ("gtin",)
    assert next_snapshot.early_stop is False
    assert next_snapshot.next_intents
    assert all(intent.fields == ("gtin",) for intent in next_snapshot.next_intents)
    assert any(intent.engine == "WEB_STRUCTURED" for intent in next_snapshot.next_intents)


def test_pdf_zero_with_exact_identity_continues_to_structured_or_web():
    orchestrator = ProductEvidenceOrchestrator(_identity(), ["gtin"])
    snapshot = orchestrator.observe_source_outcome(
        None,
        "NO_RESULT",
        engine="PDF",
        reason="NO_EXACT_DOCUMENT",
    )

    assert snapshot.early_stop is False
    assert snapshot.missing_fields == ("gtin",)
    assert any(intent.engine in {"WEB_STRUCTURED", "WEB_FALLBACK"} for intent in snapshot.next_intents)


def test_sibling_pdf_does_not_resolve_field_and_fallback_continues():
    sibling = _evidence(
        "battery_capacity",
        "4000 mAh",
        relationship="SIBLING_VARIANT",
        scope="NONE",
        policy_allowed=False,
    )
    orchestrator = ProductEvidenceOrchestrator(_identity(), ["battery_capacity"])
    snapshot = orchestrator.observe_record(
        _record(sibling),
        engine="PDF",
        source_url="https://example.test/sibling.pdf",
    )

    assert snapshot.resolved_fields == ()
    assert snapshot.missing_fields == ("battery_capacity",)
    assert snapshot.early_stop is False
    assert snapshot.next_intents


def test_sibling_web_evidence_is_also_rejected_by_shared_identity_gate():
    sibling = _evidence(
        "color",
        "Black",
        source_type="structured_web",
        authority="authorized_distributor",
        relationship="SIBLING_VARIANT",
        scope="SKU",
        policy_allowed=False,
    )
    orchestrator = ProductEvidenceOrchestrator(_identity(), ["color"])
    snapshot = orchestrator.observe_record(
        _record(sibling),
        engine="WEB_STRUCTURED",
        source_url="https://example.test/sibling",
    )

    assert snapshot.resolved_fields == ()
    assert snapshot.missing_fields == ("color",)


def test_gtin_prefers_structured_identity_sources_before_pdf():
    plan = plan_field("gtin")
    intents = route_sources(_identity(), (plan,))

    assert plan.field_kind == "IDENTIFIER"
    assert plan.required_scope == "SKU"
    assert intents[0].engine in {"EXISTING", "WEB_STRUCTURED", "IDENTITY"}
    pdf_index = next((i for i, intent in enumerate(intents) if intent.engine == "PDF"), 999)
    structured_index = next(i for i, intent in enumerate(intents) if intent.engine in {"EXISTING", "WEB_STRUCTURED", "IDENTITY"})
    assert structured_index < pdf_index


def test_technical_driver_prefers_pdf_or_manufacturer():
    plan = plan_field("driver_size")
    intents = route_sources(_identity(), (plan,))

    assert plan.field_kind == "TECHNICAL"
    assert intents[0].engine in {"PDF", "WEB_STRUCTURED"}
    assert intents[0].source_kind in {"OFFICIAL_PDF", "MANUFACTURER", "MANUFACTURER_SUPPORT"}


def test_resolved_field_is_not_searched_again_without_conflict():
    orchestrator = ProductEvidenceOrchestrator(_identity(), ["battery_capacity", "driver_size"])
    orchestrator.observe_record(
        _record(_evidence("battery_capacity", "5000 mAh")),
        engine="PDF",
        source_url="https://example.test/spec.pdf",
    )
    snapshot = orchestrator.plan_next()

    assert snapshot.missing_fields == ("driver_size",)
    assert snapshot.next_intents
    assert all("battery_capacity" not in intent.fields for intent in snapshot.next_intents)


def test_unresolved_field_conflict_is_blocking_and_not_counted_as_verified():
    rec = _record(
        _evidence("weight", "252 g"),
        conflicts=[{"attribute": "weight", "severity": "HARD", "status": "UNRESOLVED"}],
    )
    orchestrator = ProductEvidenceOrchestrator(_identity(), ["weight"])
    snapshot = orchestrator.observe_record(rec, engine="WEB_STRUCTURED", source_url="https://example.test/a")

    assert snapshot.resolved_fields == ()
    assert snapshot.conflicted_fields == ("weight",)
    assert snapshot.early_stop is True
    assert snapshot.stop_reason == "UNRESOLVED_HARD_CONFLICT"


def test_orchestrator_uses_one_hard_budget_for_the_product():
    budget = ResolutionBudget(
        max_search_queries_per_product=2,
        max_candidates_per_query=2,
        max_pages_fetched_per_product=2,
        max_pdfs_analyzed_per_product=1,
        max_sources_accepted_per_product=1,
    )
    orchestrator = ProductEvidenceOrchestrator(_identity(), ["battery_capacity"], budget=budget)

    assert orchestrator.budget_tracker.reserve_query() is True
    assert orchestrator.budget_tracker.reserve_query() is True
    assert orchestrator.budget_tracker.reserve_query() is False

    snapshot = orchestrator.plan_next()
    assert snapshot.early_stop is True
    assert snapshot.stop_reason == "SEARCH_QUERY_BUDGET"
