from __future__ import annotations

from . import document_discovery as core
from .models import ProductIdentity


def build_review_query_tiers(identity: ProductIdentity, official_domain: str | None = None) -> list[list[str]]:
    """Put distinct, high-value PDF intents inside the scarce runtime budget.

    The core ladder remains the fallback source of proven queries. This review-specific
    ordering prevents equivalent plain `MPN pdf` variants from consuming slots before
    official-domain, specifications, datasheet, manual, and support intents run.
    """
    brand = str(identity.brand or "").strip()
    model = core._descriptive_model(identity)
    strong_values = core._strong_identifiers(identity)
    domain = core._clean_official_domain(official_domain)

    priority: list[str] = []
    for strong in strong_values:
        if domain:
            priority.append(f'site:{domain} "{strong}" filetype:pdf')
        priority.extend(
            [
                f'"{strong}" filetype:pdf',
                f'"{strong}" specifications filetype:pdf',
                f'"{strong}" datasheet filetype:pdf',
                f'"{strong}" manual filetype:pdf',
                f'"{strong}" support downloads',
            ]
        )
        if brand and model:
            priority.append(f'"{brand} {model}" filetype:pdf')
        elif model:
            priority.append(f'"{model}" filetype:pdf')
        if domain and model:
            priority.append(f'site:{domain} "{model}" filetype:pdf')

    existing = core.build_document_query_tiers(identity, official_domain=official_domain)
    seen: set[str] = set()

    def unique(rows: list[str]) -> list[str]:
        result: list[str] = []
        for query in rows:
            normalized = " ".join(str(query or "").split()).strip()
            key = normalized.lower().replace('"', "")
            if not normalized or key in seen:
                continue
            seen.add(key)
            result.append(normalized)
        return result

    tiers: list[list[str]] = []
    primary = unique(priority)
    if primary:
        tiers.append(primary)
    for tier in existing:
        fallback = unique(list(tier))
        if fallback:
            tiers.append(fallback)
    return tiers


def discover_review_product_documents(
    identity: ProductIdentity,
    *,
    limit: int = 6,
    timeout: int = 8,
    trace=None,
    official_domain: str | None = None,
):
    """Document discovery for the reviewed-PDF phase; never performs OCR/Mistral."""
    tiers = build_review_query_tiers(identity, official_domain=official_domain)
    seen: set[str] = set()
    per_query = max(4, min(limit, 6))
    landing_budget = [0]
    inspected_landings: set[str] = set()
    query_attempts = 0

    for tier_index, tier in enumerate(tiers):
        if query_attempts >= core.MAX_QUERY_ATTEMPTS:
            break
        tier_valid = []
        for query in tier:
            if query_attempts >= core.MAX_QUERY_ATTEMPTS:
                break
            query_attempts += 1
            candidates = core.search_web_query_candidates(
                identity,
                query,
                limit=per_query,
                timeout=timeout,
                trace=trace,
            )
            for candidate in candidates:
                canonical = core._canonical_url(candidate.url)
                if canonical in seen:
                    if trace:
                        trace.emit("PDF_CANDIDATE_DUPLICATE", url=candidate.url)
                    continue
                seen.add(canonical)
                accepted = core._accept_search_candidate(identity, candidate, trace=trace)
                if accepted is None:
                    continue
                tier_valid.append(accepted)
                if trace and not core._looks_like_direct_pdf(accepted.url) and accepted.identity_score >= 88:
                    trace.emit("PDF_EXACT_PDP_FOUND", url=accepted.url, identity_score=accepted.identity_score)

            exact_landings = [
                row for row in tier_valid
                if not core._looks_like_direct_pdf(row.url) and row.identity_score >= 88
            ]
            if exact_landings and landing_budget[0] < core.MAX_LANDING_INSPECTIONS:
                if trace:
                    trace.emit("PDF_PDP_PIVOT", count=len(exact_landings), tier=tier_index + 1)
                resolved = core._resolve_valid_candidates(
                    identity,
                    exact_landings,
                    limit=limit,
                    timeout=timeout,
                    trace=trace,
                    landing_budget=landing_budget,
                    inspected_landings=inspected_landings,
                )
                if resolved:
                    return resolved

            if len(tier_valid) >= max(3, limit) and landing_budget[0] < core.MAX_LANDING_INSPECTIONS:
                resolved = core._resolve_valid_candidates(
                    identity,
                    tier_valid,
                    limit=limit,
                    timeout=timeout,
                    trace=trace,
                    landing_budget=landing_budget,
                    inspected_landings=inspected_landings,
                )
                if resolved:
                    return resolved

        if tier_valid and landing_budget[0] < core.MAX_LANDING_INSPECTIONS:
            resolved = core._resolve_valid_candidates(
                identity,
                tier_valid,
                limit=limit,
                timeout=timeout,
                trace=trace,
                landing_budget=landing_budget,
                inspected_landings=inspected_landings,
            )
            if resolved:
                return resolved

    flattened = [query for tier in tiers for query in tier]
    if landing_budget[0] < core.MAX_LANDING_INSPECTIONS:
        browser_resolved = core._browser_document_pass(
            identity,
            queries=flattened,
            seen=seen,
            limit=limit,
            timeout=timeout,
            trace=trace,
            landing_budget=landing_budget,
            inspected_landings=inspected_landings,
        )
        if browser_resolved:
            return browser_resolved

    fallback = []
    for candidate in core.search_web(identity, limit=max(8, limit), timeout=max(10, timeout)):
        canonical = core._canonical_url(candidate.url)
        if canonical in seen:
            continue
        seen.add(canonical)
        accepted = core._accept_search_candidate(identity, candidate, trace=trace)
        if accepted is not None:
            fallback.append(accepted)
        if len(fallback) >= 6:
            break
    return core._resolve_valid_candidates(
        identity,
        fallback,
        limit=limit,
        timeout=timeout,
        trace=trace,
        landing_budget=landing_budget,
        inspected_landings=inspected_landings,
    )
