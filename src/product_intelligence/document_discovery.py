from __future__ import annotations

import re
from urllib.parse import urlparse

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


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", key_norm(value or ""))


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


def build_document_queries(identity: ProductIdentity, official_domain: str | None = None) -> list[str]:
    """Build precision-first document queries from every available identity key.

    Search operators accelerate discovery only; downstream content validation remains
    authoritative. Query ordering intentionally preserves the historically useful
    human-verifiable primary query while spreading the bounded search budget across
    every available strong identifier before deeper expansions.
    """
    brand = str(identity.brand or "").strip()
    model = _descriptive_model(identity)
    strong_values = _strong_identifiers(identity)
    domain = _clean_official_domain(official_domain)
    queries: list[str] = []

    # Keep the proven plain Part Number/primary-identifier query first.
    if strong_values:
        queries.append(f"{strong_values[0]} pdf")

    # Exact PDF intent for every strong identifier so EAN/UPC/GTIN are not starved
    # behind the MPN when discovery executes a bounded prefix.
    for strong in strong_values:
        queries.append(f'"{strong}" filetype:pdf')

    # Bind every identifier to the descriptive model.
    if model:
        for strong in strong_values:
            queries.append(f'"{strong}" "{model}" filetype:pdf')

    # Bind every identifier to the resolved brand. Brand is corroboration, never a
    # substitute for the identifier itself.
    if brand:
        for strong in strong_values:
            queries.append(f'"{brand}" "{strong}" filetype:pdf')

    # Resilient plain-text fallbacks for transports that ignore search operators.
    for strong in strong_values:
        quoted = f'"{strong}"'
        queries.extend([
            f"{strong} pdf",
            f"{quoted} pdf",
            f"{quoted} datasheet pdf",
            f"{quoted} manual pdf",
            f"{quoted} specifications pdf",
            f"{quoted} support downloads",
            quoted,
        ])

    if brand and model:
        phrase = f'"{brand} {model}"'
        queries.extend([
            f"{phrase} datasheet pdf",
            f"{phrase} manual pdf",
            f"{phrase} filetype:pdf",
            f"{phrase} support downloads",
        ])

    # Official-domain scoping is useful only after authority has already been resolved.
    # It narrows discovery; it never marks a result as valid or official by itself.
    if domain:
        for strong in strong_values:
            queries.extend([
                f'site:{domain} "{strong}"',
                f'site:{domain} "{strong}" filetype:pdf',
                f'site:{domain} "{strong}" datasheet',
                f'site:{domain} "{strong}" manual',
            ])
        if model:
            queries.extend([
                f'site:{domain} "{model}" filetype:pdf',
                f'site:{domain} "{model}" datasheet',
                f'site:{domain} "{model}" manual',
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
    return int(bool(candidate.likely_official)), priority + support_hint, float(candidate.score or 0)


def _looks_like_direct_pdf(url: str | None) -> bool:
    return ".pdf" in str(url or "").lower()


def _is_generic_non_product_pdf(url: str, title: str = "", snippet: str = "") -> bool:
    return bool(_NON_PRODUCT_PDF.search(f"{url} {title} {snippet}"))


def _resolved_candidate(candidate: SearchCandidate, url: str, label: str = "") -> SearchCandidate:
    return SearchCandidate(
        url,
        label or candidate.title,
        f"document link from {candidate.url}",
        max(float(candidate.score or 0), .5),
        bool(candidate.likely_official),
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
        if row.url in seen or not _looks_like_direct_pdf(row.url):
            continue
        if _is_generic_non_product_pdf(row.url, row.label, ""):
            continue
        seen.add(row.url)
        resolved.append(_resolved_candidate(candidate, row.url, row.label))
        if trace:
            trace.emit("PDF_LINK_DISCOVERED", url=row.url, landing_url=candidate.url, rendered=False)

    if not resolved:
        for url, label in browser_pdf_links(candidate.url, timeout=max(timeout, 10), limit=20):
            if url in seen or not _looks_like_direct_pdf(url):
                continue
            if _is_generic_non_product_pdf(url, label, ""):
                continue
            seen.add(url)
            resolved.append(_resolved_candidate(candidate, url, label))
            if trace:
                trace.emit("PDF_LINK_DISCOVERED", url=url, landing_url=candidate.url, rendered=True)
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
            if row.url in resolved_seen or not _looks_like_direct_pdf(row.url):
                continue
            if _is_generic_non_product_pdf(row.url, row.title, row.snippet):
                continue
            resolved_seen.add(row.url)
            resolved.append(row)
            if len(resolved) >= limit:
                return resolved
    return resolved


def _browser_document_pass(identity: ProductIdentity, *, queries: list[str], seen: set[str], limit: int, timeout: int, trace=None) -> list[SearchCandidate]:
    per_query = max(6, min(max(limit * 2, 10), 16))
    collected: list[SearchCandidate] = []
    for query in queries[:4]:
        if trace:
            trace.emit("PDF_SEARCH_BROWSER_FALLBACK", query=query, reason="NO_RESOLVABLE_PDF")
        rows = browser_search(query, timeout=max(10, timeout), limit=per_query)
        if trace:
            trace.emit("PDF_SEARCH_BROWSER_RESULT", query=query, result_count=len(rows))
        for candidate in _rank_candidates(rows, identity, per_query):
            if candidate.url in seen:
                continue
            if not identity_matches_document(identity, candidate.url, candidate.title, candidate.snippet):
                continue
            if _is_generic_non_product_pdf(candidate.url, candidate.title, candidate.snippet):
                continue
            seen.add(candidate.url)
            if _looks_like_direct_pdf(candidate.url) and not classify_document_candidate(candidate.url, candidate.title, candidate.snippet):
                continue
            collected.append(candidate)
        resolved = _resolve_valid_candidates(identity, collected, limit=limit, timeout=timeout, trace=trace)
        if resolved:
            return resolved
    return []


def discover_product_documents(identity: ProductIdentity, limit: int = 6, timeout: int = 8, trace=None, official_domain: str | None = None) -> list[SearchCandidate]:
    queries = build_document_queries(identity, official_domain=official_domain)
    seen: set[str] = set()
    valid: list[SearchCandidate] = []
    per_query = max(4, min(limit, 6))
    # Execute a wider but still bounded prefix because the query matrix now spreads
    # strong identifiers across phases. Early success below still stops unnecessary work.
    for query in queries[:12]:
        candidates = search_web_query_candidates(identity, query, limit=per_query, timeout=timeout, trace=trace) if trace else search_web_query_candidates(identity, query, limit=per_query, timeout=timeout)
        for candidate in candidates:
            if candidate.url in seen:
                continue
            seen.add(candidate.url)
            if not identity_matches_document(identity, candidate.url, candidate.title, candidate.snippet):
                continue
            if _is_generic_non_product_pdf(candidate.url, candidate.title, candidate.snippet):
                continue
            if _looks_like_direct_pdf(candidate.url) and not classify_document_candidate(candidate.url, candidate.title, candidate.snippet):
                continue
            valid.append(candidate)
        if len(valid) >= 8:
            break

    resolved = _resolve_valid_candidates(identity, valid, limit=limit, timeout=timeout, trace=trace)
    if resolved:
        return resolved

    browser_resolved = _browser_document_pass(identity, queries=queries, seen=seen, limit=limit, timeout=timeout, trace=trace)
    if browser_resolved:
        return browser_resolved

    fallback: list[SearchCandidate] = []
    for candidate in search_web(identity, limit=max(8, limit), timeout=max(10, timeout)):
        if candidate.url in seen:
            continue
        seen.add(candidate.url)
        if not identity_matches_document(identity, candidate.url, candidate.title, candidate.snippet):
            continue
        if _is_generic_non_product_pdf(candidate.url, candidate.title, candidate.snippet):
            continue
        if _looks_like_direct_pdf(candidate.url) and not classify_document_candidate(candidate.url, candidate.title, candidate.snippet):
            continue
        fallback.append(candidate)
        if len(fallback) >= 8:
            break
    return _resolve_valid_candidates(identity, fallback, limit=limit, timeout=timeout, trace=trace)
