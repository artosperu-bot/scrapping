from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

from .browser_search import browser_search
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


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", key_norm(value or ""))


def _descriptive_model(identity: ProductIdentity) -> str:
    strong = {_compact(x) for x in [identity.mpn, identity.ean, identity.upc, identity.gtin] if x}
    for value in [identity.model, identity.product_name]:
        text = str(value or "").strip()
        if text and _compact(text) not in strong:
            return text
    return str(identity.model or identity.product_name or "").strip()


def build_document_queries(identity: ProductIdentity) -> list[str]:
    brand = str(identity.brand or "").strip()
    model = _descriptive_model(identity)
    strong = next((str(x).strip() for x in [identity.mpn, identity.ean, identity.upc, identity.gtin] if x), "")
    queries: list[str] = []
    if strong:
        quoted = f'"{strong}"'
        queries.extend([
            f"{strong} pdf",
            f"{quoted} pdf",
            f"{quoted} filetype:pdf",
            f"{quoted} manual pdf",
            f"{quoted} datasheet pdf",
            f"{quoted} spec sheet pdf",
            f"{quoted} specifications pdf",
            f"{quoted} user manual filetype:pdf",
            f"{quoted} support downloads",
            quoted,
        ])
    if brand and model:
        phrase = f'"{brand} {model}"'
        queries.extend([
            f"{phrase} manual pdf",
            f"{phrase} datasheet pdf",
            f"{phrase} specifications pdf",
            f"{phrase} user manual",
            f"{phrase} filetype:pdf",
            f"{phrase} support downloads",
        ])
    return list(dict.fromkeys(q for q in queries if q.strip()))


def classify_document_candidate(url: str, title: str = "", snippet: str = "") -> str | None:
    text = f"{url} {title} {snippet}"
    if _PROMOTIONAL.search(text):
        return None
    for kind, pattern in _DOCUMENT_PATTERNS:
        if pattern.search(text):
            return kind
    return None


def identity_matches_document(identity: ProductIdentity, url: str, title: str = "", snippet: str = "") -> bool:
    combined = f"{url} {title} {snippet}"
    compact = _compact(combined)
    strong = [_compact(x) for x in [identity.mpn, identity.ean, identity.upc, identity.gtin] if x]
    if any(x and x in compact for x in strong):
        return True

    brand = _compact(identity.brand)
    model_text = _descriptive_model(identity)
    model = _compact(model_text)
    if not model:
        return False

    model_tokens = re.findall(r"[a-z]+|\d+", key_norm(model_text))
    numeric_tokens = [x for x in model_tokens if x.isdigit() and len(x) >= 2]
    text_norm = key_norm(combined)
    if brand and brand in compact:
        for number in numeric_tokens:
            family_words = [x for x in model_tokens if x.isalpha() and len(x) >= 3]
            if family_words and any(word in text_norm for word in family_words):
                seen_numbers = re.findall(r"\b\d{2,}\b", text_norm)
                if seen_numbers and number not in seen_numbers:
                    return False
        return model in compact
    return False


def _search_query_with_fallback(
    identity: ProductIdentity,
    query: str,
    *,
    limit: int,
    timeout: int,
    trace=None,
) -> list[SearchCandidate]:
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
    browser_rows = browser_search(query, timeout=max(timeout, 15), limit=max(limit * 2, 12))
    if trace:
        trace.emit("PDF_SEARCH_BROWSER_RESULT", query=query, result_count=len(browser_rows))
    return _rank_candidates(browser_rows, identity, limit)


def search_web_query_candidates(
    identity: ProductIdentity,
    query: str,
    limit: int = 8,
    timeout: int = 15,
    trace=None,
) -> list[SearchCandidate]:
    if not str(query or "").strip():
        return []
    return _search_query_with_fallback(
        identity,
        str(query).strip(),
        limit=limit,
        timeout=timeout,
        trace=trace,
    )


def _document_rank(candidate: SearchCandidate) -> tuple[int, int, float]:
    kind = classify_document_candidate(candidate.url, candidate.title, candidate.snippet)
    priority = {"manual": 5, "datasheet": 5, "quick_start": 4, "compliance": 3, "technical_pdf": 2}.get(kind, 0)
    host = (urlparse(candidate.url).hostname or "").lower()
    support_hint = int(any(x in host or x in candidate.url.lower() for x in ["support", "manual", "download", "docs"]))
    return int(bool(candidate.likely_official)), priority + support_hint, float(candidate.score or 0)


def _looks_like_direct_pdf(url: str | None) -> bool:
    return (urlparse(str(url or "")).path or "").lower().endswith(".pdf")


def resolve_document_candidate_urls(
    identity: ProductIdentity,
    candidate: SearchCandidate,
    *,
    timeout: int = 15,
    trace=None,
) -> list[SearchCandidate]:
    """Turn an identity-matched landing page into concrete PDF candidates.

    HTML may be fetched only as a discovery bridge. It is never returned as
    Solo-PDF evidence; only concrete PDF URLs leave this function.
    """
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
        if row.url in seen or not _looks_like_direct_pdf(row.url):
            continue
        seen.add(row.url)
        resolved_row = SearchCandidate(
            row.url,
            row.label or candidate.title,
            f"document link from {candidate.url}",
            max(float(candidate.score or 0), .5),
            bool(candidate.likely_official),
        )
        resolved.append(resolved_row)
        if trace:
            trace.emit("PDF_LINK_DISCOVERED", url=row.url, landing_url=candidate.url)
    return resolved


def _resolve_valid_candidates(
    identity: ProductIdentity,
    candidates: list[SearchCandidate],
    *,
    limit: int,
    timeout: int,
    trace=None,
) -> list[SearchCandidate]:
    resolved: list[SearchCandidate] = []
    resolved_seen: set[str] = set()
    for candidate in sorted(candidates, key=_document_rank, reverse=True):
        try:
            if trace:
                rows = resolve_document_candidate_urls(identity, candidate, timeout=timeout, trace=trace)
            else:
                rows = resolve_document_candidate_urls(identity, candidate, timeout=timeout)
        except requests.RequestException:
            continue
        for row in rows:
            if row.url in resolved_seen or not _looks_like_direct_pdf(row.url):
                continue
            # The parent candidate already passed product identity. A PDF found
            # inside that landing may have an opaque filename/label, so do not
            # discard it before download. The PDF body is identity-validated by
            # process_pdf_document before any evidence can be accepted.
            resolved_seen.add(row.url)
            resolved.append(row)
            if len(resolved) >= limit:
                return resolved
    return resolved


def _browser_document_pass(
    identity: ProductIdentity,
    *,
    queries: list[str],
    seen: set[str],
    limit: int,
    timeout: int,
    trace=None,
) -> list[SearchCandidate]:
    """Force a browser pass when HTTP produced no concrete usable PDF."""
    per_query = max(6, min(max(limit * 2, 12), 20))
    collected: list[SearchCandidate] = []
    # Strong-ID queries are intentionally first. Stop as soon as a concrete PDF
    # is resolved rather than opening a browser for every variant unnecessarily.
    for query in queries[:8]:
        if trace:
            trace.emit("PDF_SEARCH_BROWSER_FALLBACK", query=query, reason="NO_RESOLVABLE_PDF")
        rows = browser_search(query, timeout=max(15, timeout), limit=per_query)
        if trace:
            trace.emit("PDF_SEARCH_BROWSER_RESULT", query=query, result_count=len(rows))
        for candidate in _rank_candidates(rows, identity, per_query):
            if candidate.url in seen:
                continue
            if not identity_matches_document(identity, candidate.url, candidate.title, candidate.snippet):
                continue
            seen.add(candidate.url)
            if _looks_like_direct_pdf(candidate.url) and not classify_document_candidate(
                candidate.url, candidate.title, candidate.snippet
            ):
                # Direct search hits still need document semantics in the search
                # result. Opaque PDFs discovered inside an identity-matched
                # landing are allowed later and body-validated after download.
                continue
            collected.append(candidate)
        resolved = _resolve_valid_candidates(
            identity,
            collected,
            limit=limit,
            timeout=timeout,
            trace=trace,
        )
        if resolved:
            return resolved
    return []


def discover_product_documents(
    identity: ProductIdentity,
    limit: int = 8,
    timeout: int = 15,
    trace=None,
) -> list[SearchCandidate]:
    queries = build_document_queries(identity)
    seen: set[str] = set()
    valid: list[SearchCandidate] = []
    per_query = max(4, min(limit, 8))
    for query in queries:
        if trace:
            candidates = search_web_query_candidates(identity, query, limit=per_query, timeout=timeout, trace=trace)
        else:
            candidates = search_web_query_candidates(identity, query, limit=per_query, timeout=timeout)
        for candidate in candidates:
            if candidate.url in seen:
                continue
            seen.add(candidate.url)
            if not identity_matches_document(identity, candidate.url, candidate.title, candidate.snippet):
                continue
            if _looks_like_direct_pdf(candidate.url) and not classify_document_candidate(
                candidate.url, candidate.title, candidate.snippet
            ):
                continue
            valid.append(candidate)

    resolved = _resolve_valid_candidates(identity, valid, limit=limit, timeout=timeout, trace=trace)
    if resolved:
        return resolved

    # A page result is not success. If the HTTP path found pages but none yielded
    # a concrete PDF, force a real Chromium search pass before giving up.
    browser_resolved = _browser_document_pass(
        identity,
        queries=queries,
        seen=seen,
        limit=limit,
        timeout=timeout,
        trace=trace,
    )
    if browser_resolved:
        return browser_resolved

    fallback: list[SearchCandidate] = []
    for candidate in search_web(identity, limit=max(12, limit), timeout=max(15, timeout)):
        if candidate.url in seen:
            continue
        seen.add(candidate.url)
        if not identity_matches_document(identity, candidate.url, candidate.title, candidate.snippet):
            continue
        if _looks_like_direct_pdf(candidate.url) and not classify_document_candidate(
            candidate.url, candidate.title, candidate.snippet
        ):
            continue
        fallback.append(candidate)

    return _resolve_valid_candidates(identity, fallback, limit=limit, timeout=timeout, trace=trace)
