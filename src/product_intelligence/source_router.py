from __future__ import annotations

from dataclasses import dataclass

from .field_resolution_planner import (
    COMPATIBILITY,
    GENERAL,
    IDENTIFIER,
    PACKAGE,
    SKU_VARIANT,
    TECHNICAL,
    WARRANTY_REGIONAL,
    FieldPlan,
)
from .models import ProductIdentity
from .source_strategy import SourceStrategy


@dataclass(frozen=True)
class SourceIntent:
    engine: str
    tier: str
    source_kind: str
    fields: tuple[str, ...]
    required_scope: str
    reason: str
    expected_value: float


def _history_keys(history) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for row in history or ():
        if isinstance(row, dict):
            status = str(row.get("status") or "").upper()
            if status not in {"NO_RESULT", "BLOCKED", "SOURCE_BLOCKED", "UNAVAILABLE"}:
                continue
            out.add((str(row.get("engine") or ""), str(row.get("source_kind") or "")))
        else:
            status = str(getattr(row, "status", "") or "").upper()
            if status not in {"NO_RESULT", "BLOCKED", "SOURCE_BLOCKED", "UNAVAILABLE"}:
                continue
            out.add((str(getattr(row, "engine", "") or ""), str(getattr(row, "source_kind", "") or "")))
    return out


def _intent(engine: str, tier: str, source_kind: str, plan: FieldPlan, reason: str, expected_value: float) -> SourceIntent:
    return SourceIntent(engine, tier, source_kind, (plan.field,), plan.required_scope, reason, expected_value)


def _technical_routes(plan: FieldPlan, strategy: SourceStrategy, category: str) -> list[SourceIntent]:
    routes: list[SourceIntent] = []
    cat = str(category or "GENERAL").upper()

    if cat == "PRINTER":
        if strategy.web:
            routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER_SUPPORT", plan, "PRINTER_SUPPORT_TECHNICAL_SOURCE", .99))
        if strategy.pdf:
            routes.append(_intent("PDF", "MANUFACTURER", "OFFICIAL_PDF", plan, "PRINTER_OFFICIAL_DATASHEET", .96))
        if strategy.web:
            routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER", plan, "PRINTER_MANUFACTURER_SPECIFICATIONS", .93))
            routes.append(_intent("WEB_STRUCTURED", "PRODUCT_CONTENT", "PRODUCT_CONTENT", plan, "PRINTER_STRUCTURED_CONTENT", .75))
        return routes

    if cat in {"SMARTPHONE", "COMPUTER", "PC_COMPONENT", "NETWORK"}:
        if strategy.web:
            routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER", plan, "CATEGORY_PREFERS_MANUFACTURER_TECHNICAL_PAGE", .99))
        if strategy.pdf:
            routes.append(_intent("PDF", "MANUFACTURER", "OFFICIAL_PDF", plan, "CATEGORY_OFFICIAL_TECHNICAL_DOCUMENT", .95))
        if strategy.web:
            routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER_SUPPORT", plan, "CATEGORY_OFFICIAL_SUPPORT", .90))
            if cat == "PC_COMPONENT":
                routes.append(_intent("WEB_STRUCTURED", "CATEGORY_PROVIDER", "CATEGORY_PROVIDER", plan, "PC_COMPONENT_TECHNICAL_PROVIDER", .84))
            routes.append(_intent("WEB_STRUCTURED", "PRODUCT_CONTENT", "PRODUCT_CONTENT", plan, "CATEGORY_STRUCTURED_CONTENT", .78))
        return routes

    if cat == "ELECTRONIC_COMPONENT":
        if strategy.web:
            routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER", plan, "COMPONENT_MANUFACTURER_FIRST", .99))
            routes.append(_intent("WEB_STRUCTURED", "CATEGORY_PROVIDER", "CATEGORY_PROVIDER", plan, "COMPONENT_CATEGORY_PROVIDER", .94))
        if strategy.pdf:
            routes.append(_intent("PDF", "MANUFACTURER", "OFFICIAL_PDF", plan, "COMPONENT_OFFICIAL_DATASHEET", .92))
        if strategy.web:
            routes.append(_intent("WEB_STRUCTURED", "AUTHORIZED_DISTRIBUTOR", "AUTHORIZED_DISTRIBUTOR", plan, "COMPONENT_AUTHORIZED_DISTRIBUTOR", .86))
        return routes

    # AUDIO and GENERAL technical products preserve PDF-first behavior because
    # official datasheets/manuals are usually the highest-density technical source.
    if strategy.pdf:
        routes.append(_intent("PDF", "MANUFACTURER", "OFFICIAL_PDF", plan, "TECHNICAL_SPEC_PREFERS_OFFICIAL_DOCUMENT", .98))
    if strategy.web:
        routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER", plan, "MANUFACTURER_TECHNICAL_PAGE", .94))
        routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER_SUPPORT", plan, "OFFICIAL_SUPPORT_TECHNICAL_SOURCE", .90))
        routes.append(_intent("WEB_STRUCTURED", "PRODUCT_CONTENT", "PRODUCT_CONTENT", plan, "STRUCTURED_TECHNICAL_CONTENT", .78))
    return routes


def _routes_for_plan(plan: FieldPlan, strategy: SourceStrategy, category: str) -> list[SourceIntent]:
    routes: list[SourceIntent] = []

    if plan.field_kind == IDENTIFIER:
        routes.append(_intent("EXISTING", "EXISTING_IDENTIFIERS", "EXISTING_IDENTIFIERS", plan, "VALIDATE_EXISTING_IDENTIFIER_FIRST", 1.0))
        routes.append(_intent("IDENTITY", "IDENTITY_RESOLVER", "IDENTITY_RESOLVER", plan, "RESOLVE_STRONG_PRODUCT_IDENTITY", .98))
        if strategy.web:
            routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER", plan, "EXACT_SKU_MANUFACTURER_SOURCE", .95))
            if str(category or "").upper() in {"ELECTRONIC_COMPONENT", "PC_COMPONENT"}:
                routes.append(_intent("WEB_STRUCTURED", "CATEGORY_PROVIDER", "CATEGORY_PROVIDER", plan, "CATEGORY_IDENTIFIER_PROVIDER", .92))
            routes.append(_intent("WEB_STRUCTURED", "PRODUCT_CONTENT", "PRODUCT_CONTENT", plan, "STRUCTURED_IDENTIFIER_SOURCE", .90))
            routes.append(_intent("WEB_STRUCTURED", "AUTHORIZED_DISTRIBUTOR", "AUTHORIZED_DISTRIBUTOR", plan, "AUTHORIZED_SKU_CATALOG", .82))
            routes.append(_intent("WEB_FALLBACK", "LIMITED_WEB_FALLBACK", "LIMITED_WEB", plan, "LAST_TARGETED_IDENTIFIER_FALLBACK", .45))
        return routes

    if plan.field_kind == TECHNICAL:
        routes.extend(_technical_routes(plan, strategy, category))
        if strategy.web:
            routes.append(_intent("WEB_FALLBACK", "LIMITED_WEB_FALLBACK", "LIMITED_WEB", plan, "LAST_TARGETED_TECHNICAL_FALLBACK", .42))
        return routes

    if plan.field_kind == WARRANTY_REGIONAL:
        if strategy.web:
            routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER_SUPPORT", plan, "REGIONAL_WARRANTY_PREFERS_OFFICIAL_SUPPORT", .98))
            routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER", plan, "OFFICIAL_REGIONAL_PRODUCT_POLICY", .92))
            routes.append(_intent("WEB_STRUCTURED", "AUTHORIZED_DISTRIBUTOR", "AUTHORIZED_DISTRIBUTOR", plan, "AUTHORIZED_REGIONAL_POLICY", .72))
            routes.append(_intent("WEB_FALLBACK", "LIMITED_WEB_FALLBACK", "LIMITED_WEB", plan, "LAST_TARGETED_WARRANTY_FALLBACK", .38))
        return routes

    if plan.field_kind in {SKU_VARIANT, PACKAGE}:
        if strategy.web:
            routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER", plan, "SKU_SENSITIVE_FIELD_REQUIRES_EXACT_SKU_SOURCE", .98))
            if str(category or "").upper() in {"ELECTRONIC_COMPONENT", "PC_COMPONENT"}:
                routes.append(_intent("WEB_STRUCTURED", "CATEGORY_PROVIDER", "CATEGORY_PROVIDER", plan, "CATEGORY_EXACT_SKU_SOURCE", .91))
            routes.append(_intent("WEB_STRUCTURED", "PRODUCT_CONTENT", "PRODUCT_CONTENT", plan, "STRUCTURED_SKU_CONTENT", .88))
            routes.append(_intent("WEB_STRUCTURED", "AUTHORIZED_DISTRIBUTOR", "AUTHORIZED_DISTRIBUTOR", plan, "AUTHORIZED_EXACT_SKU_SOURCE", .80))
        if strategy.pdf and plan.field_kind == PACKAGE:
            routes.append(_intent("PDF", "MANUFACTURER", "OFFICIAL_PDF", plan, "EXACT_SKU_DOCUMENT_IF_AVAILABLE", .62))
        if strategy.web:
            routes.append(_intent("WEB_FALLBACK", "LIMITED_WEB_FALLBACK", "LIMITED_WEB", plan, "LAST_TARGETED_SKU_FALLBACK", .35))
        return routes

    if plan.field_kind == COMPATIBILITY:
        if strategy.web:
            routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER_SUPPORT", plan, "COMPATIBILITY_PREFERS_OFFICIAL_SUPPORT", .96))
        if strategy.pdf:
            routes.append(_intent("PDF", "MANUFACTURER", "OFFICIAL_PDF", plan, "OFFICIAL_MANUAL_OR_GUIDE", .88))
        if strategy.web:
            routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER", plan, "OFFICIAL_PRODUCT_COMPATIBILITY", .84))
            routes.append(_intent("WEB_FALLBACK", "LIMITED_WEB_FALLBACK", "LIMITED_WEB", plan, "LAST_TARGETED_COMPATIBILITY_FALLBACK", .35))
        return routes

    # GENERAL: prefer manufacturer, then technical document, then structured content.
    if strategy.web:
        routes.append(_intent("WEB_STRUCTURED", "MANUFACTURER", "MANUFACTURER", plan, "BEST_GENERAL_AUTHORITY", .92))
    if strategy.pdf:
        routes.append(_intent("PDF", "MANUFACTURER", "OFFICIAL_PDF", plan, "OFFICIAL_DOCUMENT_GENERAL_EVIDENCE", .84))
    if strategy.web:
        routes.append(_intent("WEB_STRUCTURED", "PRODUCT_CONTENT", "PRODUCT_CONTENT", plan, "STRUCTURED_GENERAL_CONTENT", .70))
        routes.append(_intent("WEB_STRUCTURED", "AUTHORIZED_DISTRIBUTOR", "AUTHORIZED_DISTRIBUTOR", plan, "AUTHORIZED_GENERAL_SOURCE", .62))
        routes.append(_intent("WEB_FALLBACK", "LIMITED_WEB_FALLBACK", "LIMITED_WEB", plan, "LAST_TARGETED_GENERAL_FALLBACK", .30))
    return routes


def route_sources(
    identity: ProductIdentity,
    field_plans: tuple[FieldPlan, ...] | list[FieldPlan],
    *,
    category: str | None = None,
    strategy: SourceStrategy | None = None,
    history=(),
) -> tuple[SourceIntent, ...]:
    """Return BEST-EVIDENCE-FIRST intents for unresolved fields.

    Routing depends on field semantics and generic product category, never on brand.
    Product identity remains load-bearing in the acquisition engines and identity gates.
    """
    del identity
    active = (strategy or SourceStrategy()).normalized()
    blocked = _history_keys(history)
    profile = str(category or "GENERAL").upper()
    out: list[SourceIntent] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for plan in field_plans or ():
        for intent in _routes_for_plan(plan, active, profile):
            if (intent.engine, intent.source_kind) in blocked:
                continue
            key = (intent.engine, intent.source_kind, intent.fields)
            if key in seen:
                continue
            seen.add(key)
            out.append(intent)
    return tuple(out)
