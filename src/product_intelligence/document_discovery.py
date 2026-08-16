from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse, urlsplit, urlunsplit

import requests

from .browser_search import browser_pdf_links, browser_search
from .discovery import SearchCandidate, _provider_search, _rank_candidates, search_web
from .models import ProductIdentity
from .normalize import key_norm
from .pdf_evidence import discover_pdf_candidates
from .web_fetch import UA

_DOCUMENT_PATTERNS = (
    ("quick_start", re.compile(r"\bquick\s*(?:start|guide)|gu[ií]a\s+r[aá]pida\b", re.I)),
    ("compliance", re.compile(r"\bcompliance|regulatory|declaration\s+of\s+conformity|conformidad|certification\b", re.I)),
    ("datasheet", re.compile(r"\bdata\s*sheet|datasheet|spec\s*sheet|ficha\s+t[eé]cnica|technical\s+sheet\b", re.I)),
    ("manual", re.compile(r"\buser\s+manual|owner'?s\s+manual|manual\s+de\s+usuario|manual\b", re.I)),
    ("technical_pdf", re.compile(r"\bspecifications?|technical\s+specifications?|especificaciones\b", re.I)),
)
_PROMOTIONAL = re.compile(r"\bbrochure|catalog(?:ue)?|promotional|buy\s+now|shop\s+now|oferta|sale\b", re.I)
_NON_PRODUCT_PDF = re.compile(
    r"\bprivacy|privacy[_-]?policy|terms(?:[_-]?and[_-]?conditions)?|cookies?|legal|"
    r"return[_-]?policy|shipping[_-]?policy|accessibility|sitemap\b",
    re.I,
)
_GENERIC_PAGE = re.compile(r"\b(all|category|categories|catalog|catalogue|shop|store|headphones?|audifonos?|products?)\b", re.I)


@dataclass(frozen=True)
class DocumentCandidateAssessment:
    accepted: bool
    reason: str
    identity_score: int
    exact_strong_id: bool = False
    exact_model: bool = False
    conflict: bool = False


@dataclass(frozen=True)
class DocumentProvenance:
    parent_url: str
    parent_identity_status: str
    parent_identity_confidence: float
    parent_authority: str
    anchor_text: str = ""
    discovery_method: str = "landing_link"


@dataclass
class DocumentSearchCandidate(SearchCandidate):
    provenance: DocumentProvenance | None = None
    identity_status: str = "UNVERIFIED"
    identity_reason: str = ""
    identity_score: int = 0


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", key_norm(value or ""))


def _canonical_url(url: str) -> str:
    try:
        parsed = urlsplit(str(url or "").strip())
        scheme = (parsed.scheme or "https").lower()
        host = (parsed.hostname or "").lower().removeprefix("www.")
        port = f":{parsed.port}" if parsed.port and not ((scheme == "https" and parsed.port == 443) or (scheme == "http" and parsed.port == 80)) else ""
        path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/") or "/"
        return urlunsplit((scheme, host + port, path, parsed.query, ""))
    except Exception:
        return str(url or "").strip()


def _descriptive_model(identity: ProductIdentity) -> str:
    strong = {_compact(x) for x in [identity.mpn, identity.ean, identity.upc, identity.gtin] if x}
    for value in [identity.model, identity.product_name]:
        text = str(value or "").strip()
        if text and _compact(text) not in strong:
            return text
    return str(identity.model or identity.product_name or "").strip()


def _strong_identifiers(identity: ProductIdentity) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for raw in [identity.mpn, identity.ean, identity.upc, identity.gtin]:
        value = str(raw or "").strip()
        norm = _compact(value)
        if not value or not norm or norm in seen:
            continue
        seen.add(norm)
        values.append(value)
    return values


def _clean_official_domain(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or not re.fullmatch(r"[a-z0-9.-]+", host) or "." not in host:
        return ""
    return host


def build_document_query_tiers(identity: ProductIdentity, official_domain: str | None = None) -> list[list[str]]:
    """Return a precision-first escalation ladder while preserving proven legacy queries."""
    brand = str(identity.brand or "").strip()
    model = _descriptive_model(identity)
    strong_values = _strong_identifiers(identity)
    domain = _clean_official_domain(official_domain)

    tier1: list[str] = []
    for strong in strong_values:
        tier1.extend([
            f"{strong} pdf",
            f'"{strong}" pdf',
            f'"{strong}" filetype:pdf',
            f'"{strong}" manual pdf',
            f'"{strong}" datasheet',
        ])
        if model:
            tier1.append(f'"{strong}" "{model}" filetype:pdf')
        if brand:
            tier1.append(f'"{brand}" "{strong}" filetype:pdf')
        if domain:
            tier1.extend([f'site:{domain} "{strong}"', f'site:{domain} "{strong}" filetype:pdf'])

    tier2: list[str] = []
    for strong in strong_values:
        tier2.extend([f'"{strong}" specifications', f'"{strong}" support downloads'])
    if brand and model:
        combined = f'"{brand} {model}"'
        tier2.extend([
            f"{combined} manual pdf",
            f"{combined} datasheet pdf",
            f"{combined} specifications",
            f"{combined} support",
        ])
        if domain:
            tier2.extend([
                f'site:{domain} "{model}" filetype:pdf',
                f'site:{domain} "{model}" manual',
                f'site:{domain} "{model}" datasheet',
            ])

    tier3: list[str] = []
    if brand and model:
        separated = f'"{brand}" "{model}"'
        tier3.extend([
            f"{separated} manual pdf",
            f"{separated} datasheet pdf",
            f"{separated} specifications",
            f"{separated} support",
        ])
    if model:
        tier3.extend([f'"{model}" manual pdf', f'"{model}" datasheet pdf'])

    tier4: list[str] = []
    if strong_values:
        tier4.extend([f'"{strong}"' for strong in strong_values])
    if brand and model:
        tier4.append(f"{brand} {model}")

    return [list(dict.fromkeys(x for x in tier if x.strip())) for tier in (tier1, tier2, tier3, tier4) if tier]


def build_document_queries(identity: ProductIdentity, official_domain: str | None = None) -> list[str]:
    return [query for tier in build_document_query_tiers(identity, official_domain=official_domain) for query in tier]


def _model_tokens(value: str) -> tuple[list[str], list[str]]:
    tokens = re.findall(r"[a-z]+|\d+", key_norm(value or ""))
    words = [token for token in tokens if token.isalpha() and len(token) >= 3 and token not in {"wireless", "wired", "gaming", "headset", "headphone", "headphones"}]
    numbers = [token for token in tokens if token.isdigit() and len(token) >= 1]
    return words, numbers


def assess_document_candidate(identity: ProductIdentity, url: str, title: str = "", snippet: str = "") -> DocumentCandidateAssessment:
    combined = f"{url} {title} {snippet}"
    compact = _compact(combined)
    text_norm = key_norm(combined)
    strong_values = [_compact(x) for x in _strong_identifiers(identity)]
    exact_strong = any(value and value in compact for value in strong_values)
    if exact_strong:
        return DocumentCandidateAssessment(True, "exact_strong_identifier", 100, exact_strong_id=True)

    brand = _compact(identity.brand)
    model_text = _descriptive_model(identity)
    model = _compact(model_text)
    exact_model = bool(model and model in compact and (not brand or brand in compact))
    if exact_model:
        return DocumentCandidateAssessment(True, "exact_brand_model", 88, exact_model=True)

    if brand and brand in compact:
        words, requested_numbers = _model_tokens(model_text)
        candidate_numbers = set(re.findall(r"\b\d{1,4}\b", text_norm))
        has_requested_family = any(word in text_norm for word in words) if words else False
        if requested_numbers and has_requested_family and not any(number in candidate_numbers for number in requested_numbers):
            return DocumentCandidateAssessment(False, "sibling_model_conflict", 0, conflict=True)
        if classify_document_candidate(url, title, snippet) and model and model not in compact:
            return DocumentCandidateAssessment(False, "sibling_model_conflict", 0, conflict=True)
        if _GENERIC_PAGE.search(f"{title} {snippet}"):
            return DocumentCandidateAssessment(False, "brand_only_or_generic", 10)
        return DocumentCandidateAssessment(False, "brand_only_or_generic", 15)

    return DocumentCandidateAssessment(False, "identity_not_confirmed", 0)


def identity_matches_document(identity: ProductIdentity, url: str, title: str = "", snippet: str = "") -> bool:
    return assess_document_candidate(identity, url, title, snippet).accepted


def can_bind_document_by_provenance(provenance: DocumentProvenance | None, *, internal_identity_reason: str) -> bool:
    if provenance is None:
        return False
    if str(provenance.parent_identity_status).upper() not in {"EXACT", "STRONG"}:
        return False
    if float(provenance.parent_identity_confidence or 0.0) < 0.85:
        return False
    if str(internal_identity_reason or "") in {"strong_identifier_conflict", "sibling_model_url_conflict", "identity_conflict"}:
        return False
    return str(internal_identity_reason or "") in {"strong_identifier_missing", "identity_not_confirmed"}


def classify_document_candidate(url: str, title: str = "", snippet: str = "") -> str | None:
    text = f"{url} {title} {snippet}"
    if _PROMOTIONAL.search(text):
        return None
    for kind, pattern in _DOCUMENT_PATTERNS:
        if pattern.search(text):
            return kind
    return None


def _search_query_with_fallback(identity: ProductIdentity, query: str, *, limit: int, timeout: int, trace=None) -> list[SearchCandidate]:
    if trace:
        trace.emit("PDF_SEARCH_QUERY", query=query, transport="http")
    http_rows = _provider_search(query, timeout)
    if trace:
        trace.emit("PDF_SEARCH_HTTP_RESULT", query=query, result_count=len(http_rows))
    ranked = _rank_candidates(http_rows, identity, limit)
    if ranked:
        return ranked
    if trace:
        trace.emit("PDF_SEARCH_BROWSER_FALLBACK", query=query)
    browser_rows = browser_search(query, timeout=max(timeout, 10), limit=max(limit * 2, 10))
    if trace:
        trace.emit("PDF_SEARCH_BROWSER_RESULT", query=query, result_count=len(browser_rows))
    return _rank_candidates(browser_rows, identity, limit)


def search_web_query_candidates(identity: ProductIdentity, query: str, limit: int = 6, timeout: int = 8, trace=None) -> list[SearchCandidate]:
    if not str(query or "").strip():
        return []
    return _search_query_with_fallback(identity, str(query).strip(), limit=limit, timeout=timeout, trace=trace)


def _document_rank(candidate: SearchCandidate) -> tuple[int, int, float]:
    kind = classify_document_candidate(candidate.url, candidate.title, candidate.snippet)
    priority = {"manual": 5, "datasheet": 5, "quick_start": 4, "compliance": 3, "technical_pdf": 2}.get(kind, 0)
    host = (urlparse(candidate.url).hostname or "").lower()
    support_hint = int(any(x in host or x in candidate.url.lower() for x in ["support", "manual", "download", "docs"]))
    assessment = getattr(candidate, "identity_score", 0)
    return int(bool(candidate.likely_official)), int(assessment) + priority + support_hint, float(candidate.score or 0)


def _looks_like_direct_pdf(url: str | None) -> bool:
    return ".pdf" in str(url or "").lower()


def _is_generic_non_product_pdf(url: str, title: str = "", snippet: str = "") -> bool:
    return bool(_NON_PRODUCT_PDF.search(f"{url} {title} {snippet}"))


def _resolved_candidate(candidate: SearchCandidate, url: str, label: str = "", *, provenance: DocumentProvenance | None = None) -> DocumentSearchCandidate:
    assessment_score = int(getattr(candidate, "identity_score", 0) or 0)
    return DocumentSearchCandidate(
        url=url,
        title=label or candidate.title,
        snippet=f"document link from {candidate.url}",
        score=max(float(candidate.score or 0), .5),
        likely_official=bool(candidate.likely_official),
        provenance=provenance,
        identity_status="PROVENANCE_BOUND" if provenance else str(getattr(candidate, "identity_status", "UNVERIFIED")),
        identity_reason="exact_parent_link" if provenance else str(getattr(candidate, "identity_reason", "")),
        identity_score=max(assessment_score, 85 if provenance else assessment_score),
    )


def _parent_provenance(identity: ProductIdentity, candidate: SearchCandidate, anchor_text: str, rendered: bool) -> DocumentProvenance | None:
    assessment = assess_document_candidate(identity, candidate.url, candidate.title, candidate.snippet)
    if not assessment.accepted:
        return None
    status = "EXACT" if assessment.exact_strong_id or assessment.exact_model else "STRONG"
    authority = "MANUFACTURER" if bool(candidate.likely_official) else "VALIDATED_SOURCE"
    return DocumentProvenance(
        parent_url=candidate.url,
        parent_identity_status=status,
        parent_identity_confidence=min(1.0, assessment.identity_score / 100.0),
        parent_authority=authority,
        anchor_text=anchor_text,
        discovery_method="exact_pdp_rendered_link" if rendered else "exact_pdp_link",
    )


def resolve_document_candidate_urls(identity: ProductIdentity, candidate: SearchCandidate, *, timeout: int = 8, trace=None) -> list[SearchCandidate]:
    if _looks_like_direct_pdf(candidate.url):
        if trace:
            trace.emit("PDF_LINK_DISCOVERED", url=candidate.url, direct=True)
        return [candidate]

    if trace:
        trace.emit("PDF_LANDING_INSPECTED", url=candidate.url)
    response = requests.get(
        candidate.url,
        timeout=timeout,
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.7"},
    )
    response.raise_for_status()
    resolved: list[SearchCandidate] = []
    seen: set[str] = set()
    for row in discover_pdf_candidates(response.text, candidate.url):
        canonical = _canonical_url(row.url)
        if canonical in seen or not _looks_like_direct_pdf(row.url):
            continue
        if _is_generic_non_product_pdf(row.url, row.label, ""):
            continue
        seen.add(canonical)
        provenance = _parent_provenance(identity, candidate, row.label, False)
        resolved.append(_resolved_candidate(candidate, row.url, row.label, provenance=provenance))
        if trace:
            trace.emit("PDF_LINK_DISCOVERED", url=row.url, landing_url=candidate.url, rendered=False)
            if provenance:
                trace.emit("PDF_PROVENANCE_BOUND", url=row.url, parent_url=candidate.url)

    if not resolved:
        for url, label in browser_pdf_links(candidate.url, timeout=max(timeout, 10), limit=20):
            canonical = _canonical_url(url)
            if canonical in seen or not _looks_like_direct_pdf(url):
                continue
            if _is_generic_non_product_pdf(url, label, ""):
                continue
            seen.add(canonical)
            provenance = _parent_provenance(identity, candidate, label, True)
            resolved.append(_resolved_candidate(candidate, url, label, provenance=provenance))
            if trace:
                trace.emit("PDF_LINK_DISCOVERED", url=url, landing_url=candidate.url, rendered=True)
                if provenance:
                    trace.emit("PDF_PROVENANCE_BOUND", url=url, parent_url=candidate.url)
    return resolved


def _resolve_valid_candidates(identity: ProductIdentity, candidates: list[SearchCandidate], *, limit: int, timeout: int, trace=None) -> list[SearchCandidate]:
    resolved: list[SearchCandidate] = []
    resolved_seen: set[str] = set()
    for candidate in sorted(candidates, key=_document_rank, reverse=True)[:12]:
        try:
            rows = resolve_document_candidate_urls(identity, candidate, timeout=timeout, trace=trace) if trace else resolve_document_candidate_urls(identity, candidate, timeout=timeout)
        except requests.RequestException:
            continue
        for row in rows:
            canonical = _canonical_url(row.url)
            if canonical in resolved_seen or not _looks_like_direct_pdf(row.url):
                continue
            if _is_generic_non_product_pdf(row.url, row.title, row.snippet):
                continue
            resolved_seen.add(canonical)
            resolved.append(row)
            if len(resolved) >= limit:
                return resolved
    return resolved


def _accept_search_candidate(identity: ProductIdentity, candidate: SearchCandidate, trace=None) -> DocumentSearchCandidate | None:
    assessment = assess_document_candidate(identity, candidate.url, candidate.title, candidate.snippet)
    if not assessment.accepted:
        if trace:
            trace.emit("PDF_CANDIDATE_REJECTED_PRE_FETCH", url=candidate.url, reason=assessment.reason)
        return None
    if _is_generic_non_product_pdf(candidate.url, candidate.title, candidate.snippet):
        if trace:
            trace.emit("PDF_CANDIDATE_REJECTED_PRE_FETCH", url=candidate.url, reason="non_product_document")
        return None
    if _looks_like_direct_pdf(candidate.url) and not classify_document_candidate(candidate.url, candidate.title, candidate.snippet):
        if not assessment.exact_strong_id:
            return None
    return DocumentSearchCandidate(
        url=candidate.url,
        title=candidate.title,
        snippet=candidate.snippet,
        score=candidate.score,
        likely_official=candidate.likely_official,
        identity_status="EXACT" if assessment.exact_strong_id or assessment.exact_model else "STRONG",
        identity_reason=assessment.reason,
        identity_score=assessment.identity_score,
    )


def _browser_document_pass(identity: ProductIdentity, *, queries: list[str], seen: set[str], limit: int, timeout: int, trace=None) -> list[SearchCandidate]:
    per_query = max(6, min(max(limit * 2, 10), 16))
    collected: list[SearchCandidate] = []
    for query in queries[:3]:
        if trace:
            trace.emit("PDF_SEARCH_BROWSER_FALLBACK", query=query, reason="NO_RESOLVABLE_PDF")
        rows = browser_search(query, timeout=max(10, timeout), limit=per_query)
        if trace:
            trace.emit("PDF_SEARCH_BROWSER_RESULT", query=query, result_count=len(rows))
        for candidate in _rank_candidates(rows, identity, per_query):
            canonical = _canonical_url(candidate.url)
            if canonical in seen:
                if trace:
                    trace.emit("PDF_CANDIDATE_DUPLICATE", url=candidate.url)
                continue
            seen.add(canonical)
            accepted = _accept_search_candidate(identity, candidate, trace=trace)
            if accepted is not None:
                collected.append(accepted)
        resolved = _resolve_valid_candidates(identity, collected, limit=limit, timeout=timeout, trace=trace)
        if resolved:
            return resolved
    return []


def discover_product_documents(identity: ProductIdentity, limit: int = 6, timeout: int = 8, trace=None, official_domain: str | None = None) -> list[SearchCandidate]:
    tiers = build_document_query_tiers(identity, official_domain=official_domain)
    seen: set[str] = set()
    valid: list[SearchCandidate] = []
    per_query = max(4, min(limit, 6))

    for tier_index, tier in enumerate(tiers):
        tier_valid: list[SearchCandidate] = []
        for query in tier:
            candidates = search_web_query_candidates(identity, query, limit=per_query, timeout=timeout, trace=trace) if trace else search_web_query_candidates(identity, query, limit=per_query, timeout=timeout)
            for candidate in candidates:
                canonical = _canonical_url(candidate.url)
                if canonical in seen:
                    if trace:
                        trace.emit("PDF_CANDIDATE_DUPLICATE", url=candidate.url)
                    continue
                seen.add(canonical)
                accepted = _accept_search_candidate(identity, candidate, trace=trace)
                if accepted is None:
                    continue
                tier_valid.append(accepted)
                valid.append(accepted)
                if trace and not _looks_like_direct_pdf(accepted.url) and accepted.identity_score >= 88:
                    trace.emit("PDF_EXACT_PDP_FOUND", url=accepted.url, identity_score=accepted.identity_score)

            exact_landings = [row for row in tier_valid if not _looks_like_direct_pdf(row.url) and row.identity_score >= 88]
            if exact_landings:
                if trace:
                    trace.emit("PDF_PDP_PIVOT", count=len(exact_landings), tier=tier_index + 1)
                resolved = _resolve_valid_candidates(identity, exact_landings, limit=limit, timeout=timeout, trace=trace)
                if resolved:
                    return resolved

            if len(tier_valid) >= max(3, limit):
                resolved = _resolve_valid_candidates(identity, tier_valid, limit=limit, timeout=timeout, trace=trace)
                if resolved:
                    return resolved

        if tier_valid:
            resolved = _resolve_valid_candidates(identity, tier_valid, limit=limit, timeout=timeout, trace=trace)
            if resolved:
                return resolved

    flattened_queries = [query for tier in tiers for query in tier]
    browser_resolved = _browser_document_pass(identity, queries=flattened_queries, seen=seen, limit=limit, timeout=timeout, trace=trace)
    if browser_resolved:
        return browser_resolved

    fallback: list[SearchCandidate] = []
    for candidate in search_web(identity, limit=max(8, limit), timeout=max(10, timeout)):
        canonical = _canonical_url(candidate.url)
        if canonical in seen:
            continue
        seen.add(canonical)
        accepted = _accept_search_candidate(identity, candidate, trace=trace)
        if accepted is not None:
            fallback.append(accepted)
        if len(fallback) >= 6:
            break
    return _resolve_valid_candidates(identity, fallback, limit=limit, timeout=timeout, trace=trace)