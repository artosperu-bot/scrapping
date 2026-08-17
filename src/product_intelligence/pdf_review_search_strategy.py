from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from . import document_discovery as core
from .models import ProductIdentity


@dataclass
class ReviewQueryBudget:
    """One hard logical-query budget shared by every review-discovery pass for a product."""

    limit: int = core.MAX_QUERY_ATTEMPTS
    used: int = 0
    queries: list[str] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set, repr=False)

    @property
    def remaining(self) -> int:
        return max(0, int(self.limit) - int(self.used))

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def reserve(self, query: str) -> bool:
        normalized = " ".join(str(query or "").split()).strip()
        key = normalized.lower()
        if not normalized or key in self._seen or self.exhausted:
            return False
        self._seen.add(key)
        self.queries.append(normalized)
        self.used += 1
        return True


def build_review_query_tiers(identity: ProductIdentity, official_domain: str | None = None) -> list[list[str]]:
    """Build a bounded, strategy-reserved document query plan after identity resolution.

    MAX_QUERY_ATTEMPTS remains authoritative. The first tier intentionally reserves
    slots across independent high-value strategies so verbose canonical variants
    cannot evict official-identifier, support, manual, spec or datasheet intent.
    """
    brand = str(identity.brand or identity.manufacturer or "").strip()
    model = core._descriptive_model(identity)
    strong_values = core._strong_identifiers(identity)
    domain = core._clean_official_domain(official_domain)
    seen: set[str] = set()

    def unique(rows: list[str]) -> list[str]:
        result: list[str] = []
        for query in rows:
            normalized = " ".join(str(query or "").split()).strip()
            key = normalized.lower().replace('"', "")
            if normalized and key not in seen:
                seen.add(key)
                result.append(normalized)
        return result

    primary_strong = strong_values[0] if strong_values else ""
    combined = f'"{brand} {model}"' if brand and model else f'"{model}"' if model else ""

    reserved: list[str] = []
    if domain and model:
        reserved.append(f'site:{domain} "{model}" filetype:pdf')
    if domain and primary_strong:
        reserved.append(f'site:{domain} "{primary_strong}" filetype:pdf')
    if combined:
        reserved.extend([
            f"{combined} specsheet",
            f"{combined} manual",
            f"{combined} support downloads",
        ])
    if primary_strong:
        reserved.append(f'"{primary_strong}" filetype:pdf')
    if combined:
        reserved.extend([
            f"{combined} datasheet",
            f"{combined} filetype:pdf",
        ])

    canonical: list[str] = []
    if model:
        if domain:
            canonical.extend([
                f'site:{domain} "{model}" filetype:pdf',
                f'site:{domain} "{model}" manual',
                f'site:{domain} "{model}" datasheet',
            ])
        if combined:
            canonical.extend([
                f"{combined} filetype:pdf",
                f"{combined} specsheet",
                f"{combined} datasheet",
                f"{combined} manual",
                f"{combined} support downloads",
                f'{combined} "quick start guide"',
            ])

    identifier_precision: list[str] = []
    for strong in strong_values:
        if domain:
            identifier_precision.append(f'site:{domain} "{strong}" filetype:pdf')
        identifier_precision.extend([
            f'"{strong}" filetype:pdf',
            f'"{strong}" specifications filetype:pdf',
            f'"{strong}" datasheet filetype:pdf',
            f'"{strong}" manual filetype:pdf',
            f'"{strong}" support downloads',
        ])

    tiers: list[list[str]] = []
    for rows in [reserved, canonical, identifier_precision, *core.build_document_query_tiers(identity, official_domain=official_domain)]:
        cleaned = unique(list(rows))
        if cleaned:
            tiers.append(cleaned)
    return tiers


def _on_official_domain(url: str, official_domain: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")
    domain = core._clean_official_domain(official_domain)
    return bool(host and domain and (host == domain or host.endswith("." + domain)))


def _landing_domain(url: str) -> str | None:
    host = (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")
    return core._clean_official_domain(host) if host else None


def _row_key(row) -> str:
    url = str(getattr(row, "url", "") or "").strip()
    if url:
        return core._canonical_url(url)
    if isinstance(row, str) and row:
        return f"literal:{row}"
    return ""


def _discover_official_pdp_documents(
    identity: ProductIdentity,
    *,
    official_domain: str | None,
    limit: int,
    timeout: int,
    trace=None,
    seen: set[str] | None = None,
    landing_budget: list[int] | None = None,
    inspected_landings: set[str] | None = None,
    reserve_query=None,
):
    domain = core._clean_official_domain(official_domain)
    strong_values = core._strong_identifiers(identity)
    brand = str(identity.brand or identity.manufacturer or "").strip()
    if not strong_values or (not domain and not brand):
        return []
    shared_seen = seen if seen is not None else set()
    budget = landing_budget if landing_budget is not None else [0]
    inspected = inspected_landings if inspected_landings is not None else set()
    per_query = max(4, min(max(1, int(limit)), 6))
    found = []
    found_urls: set[str] = set()

    def collect(rows):
        for row in rows or []:
            key = _row_key(row)
            if not key or key in found_urls:
                continue
            found_urls.add(key)
            found.append(row)

    for strong in strong_values[:2]:
        query_specs: list[tuple[str, bool]] = []
        if domain:
            query_specs.append((f'site:{domain} "{strong}"', True))
        if brand:
            query_specs.append((f'"{strong}" "{brand}"', False))
        for query, strict_known_domain in query_specs:
            if reserve_query is not None and not reserve_query(query):
                continue
            if trace:
                trace.emit("PDF_PDP_SEARCH", query=query, identifier=strong, domain=domain if strict_known_domain else "AUTO_BRAND_DOMAIN")
            candidates = core.search_web_query_candidates(identity, query, limit=per_query, timeout=timeout, trace=trace)
            exact_landings = []
            for candidate in candidates:
                canonical = core._canonical_url(candidate.url)
                if canonical in shared_seen:
                    continue
                shared_seen.add(canonical)
                accepted = core._accept_search_candidate(identity, candidate, trace=trace)
                if accepted is None or core._looks_like_direct_pdf(accepted.url) or accepted.identity_score < 88 or not accepted.likely_official:
                    continue
                if strict_known_domain:
                    if not _on_official_domain(accepted.url, domain):
                        continue
                    authority_domain = domain
                else:
                    authority_domain = _landing_domain(accepted.url)
                if not authority_domain:
                    continue
                exact_landings.append(accepted)
                if trace:
                    trace.emit("PDF_PDP_VALIDATED", url=accepted.url, identifier=strong, identity_score=accepted.identity_score, authority="MANUFACTURER", domain=authority_domain)
            if exact_landings and budget[0] < core.MAX_LANDING_INSPECTIONS:
                resolved = core._resolve_valid_candidates(
                    identity,
                    exact_landings,
                    limit=limit,
                    timeout=timeout,
                    trace=trace,
                    landing_budget=budget,
                    inspected_landings=inspected,
                )
                if resolved:
                    collect(resolved)
                    if trace:
                        trace.emit("PDF_PDP_DOCUMENTS_RESOLVED", count=len(resolved), parent_count=len(exact_landings))
    return found


def discover_review_product_documents(
    identity: ProductIdentity,
    *,
    limit: int = 6,
    timeout: int = 8,
    trace=None,
    official_domain: str | None = None,
    query_budget: ReviewQueryBudget | None = None,
    max_new_queries: int | None = None,
):
    """Discover candidates under one shared per-product query budget.

    Raw/resolved URLs never stop discovery before validation. When ``query_budget``
    is supplied, every logical document query across PDP-first, tiers and retries
    consumes the same hard MAX_QUERY_ATTEMPTS budget.
    """
    tiers = build_review_query_tiers(identity, official_domain=official_domain)
    seen: set[str] = set()
    per_query = max(4, min(limit, 6))
    landing_budget = [0]
    inspected_landings: set[str] = set()
    discovered = []
    discovered_urls: set[str] = set()
    shared_budget = query_budget is not None
    budget = query_budget or ReviewQueryBudget()
    pass_used = 0

    def can_reserve_more() -> bool:
        if budget.exhausted:
            return False
        return max_new_queries is None or pass_used < max(0, int(max_new_queries))

    def reserve_query(query: str) -> bool:
        nonlocal pass_used
        if not can_reserve_more():
            return False
        before = budget.used
        accepted = budget.reserve(query)
        if accepted and budget.used > before:
            pass_used += 1
        return accepted

    def collect(rows):
        added = 0
        for row in rows or []:
            key = _row_key(row)
            if not key or key in discovered_urls:
                continue
            discovered_urls.add(key)
            discovered.append(row)
            added += 1
        return added

    pdp_documents = _discover_official_pdp_documents(
        identity,
        official_domain=official_domain,
        limit=limit,
        timeout=timeout,
        trace=trace,
        seen=seen,
        landing_budget=landing_budget,
        inspected_landings=inspected_landings,
        reserve_query=reserve_query,
    )
    if collect(pdp_documents) and trace:
        trace.emit("PDF_DISCOVERY_CONTINUE_AFTER_RAW_LINKS", source="OFFICIAL_PDP", candidate_count=len(discovered))

    for tier_index, tier in enumerate(tiers):
        if not can_reserve_more():
            break
        tier_valid = []
        for query in tier:
            if not can_reserve_more():
                break
            if not reserve_query(query):
                continue
            candidates = core.search_web_query_candidates(identity, query, limit=per_query, timeout=timeout, trace=trace)
            query_valid = []
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
                query_valid.append(accepted)
                if core._looks_like_direct_pdf(accepted.url):
                    collect([accepted])
                elif trace and accepted.identity_score >= 88:
                    trace.emit("PDF_EXACT_PDP_FOUND", url=accepted.url, identity_score=accepted.identity_score)

            exact_landings = [row for row in query_valid if not core._looks_like_direct_pdf(row.url) and row.identity_score >= 88]
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
                if collect(resolved) and trace:
                    trace.emit("PDF_DISCOVERY_CONTINUE_AFTER_RAW_LINKS", source="PDP_PIVOT", candidate_count=len(discovered))

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
            if collect(resolved) and trace:
                trace.emit("PDF_DISCOVERY_CONTINUE_AFTER_RAW_LINKS", source="TIER", candidate_count=len(discovered))

    # Each normal logical query already gets an HTTP->browser transport fallback in
    # search_web_query_candidates. The separate broad browser pass would execute
    # extra searches outside that logical query and is therefore disabled whenever
    # the end-to-end shared budget is active.
    if not shared_budget:
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
            collect(browser_resolved)

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
        collect(core._resolve_valid_candidates(
            identity,
            fallback,
            limit=limit,
            timeout=timeout,
            trace=trace,
            landing_budget=landing_budget,
            inspected_landings=inspected_landings,
        ))

    if trace:
        trace.emit("PDF_QUERY_BUDGET", used=budget.used, limit=budget.limit, remaining=budget.remaining)
    discovered.sort(key=lambda row: core._document_rank(row) if hasattr(row, "url") else (0, 0, 0), reverse=True)
    return discovered[: max(1, int(limit))]
