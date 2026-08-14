from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

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
    if strong:
        quoted = f'"{strong}"'
        queries.extend([
            quoted,
            f"{quoted} support downloads",
            f"{quoted} manual pdf",
            f"{quoted} datasheet",
            f"{quoted} specifications pdf",
            f"{quoted} filetype:pdf",
            f"{quoted} spec sheet pdf",
            f"{quoted} user manual filetype:pdf",
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


def search_web_query_candidates(identity: ProductIdentity, query: str, limit: int = 8, timeout: int = 15) -> list[SearchCandidate]:
    if not str(query or "").strip():
        return []
    return _rank_candidates(_provider_search(str(query).strip(), timeout), identity, limit)


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
) -> list[SearchCandidate]:
    """Turn an identity-matched landing page into concrete PDF candidates.

    In PDF-only mode HTML may be fetched only as a discovery bridge. It is never
    returned as evidence. Final candidates from this function are concrete PDFs;
    downstream PDF ingestion still validates the document contents against the
    product identity before any evidence is accepted.
    """
    if _looks_like_direct_pdf(candidate.url):
        return [candidate]

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
        resolved.append(SearchCandidate(
            row.url,
            row.label or candidate.title,
            f"document link from {candidate.url}",
            max(float(candidate.score or 0), .5),
            bool(candidate.likely_official),
        ))
    return resolved


def _resolve_valid_candidates(
    identity: ProductIdentity,
    candidates: list[SearchCandidate],
    *,
    limit: int,
    timeout: int,
) -> list[SearchCandidate]:
    resolved: list[SearchCandidate] = []
    resolved_seen: set[str] = set()
    for candidate in sorted(candidates, key=_document_rank, reverse=True):
        try:
            rows = resolve_document_candidate_urls(identity, candidate, timeout=timeout)
        except requests.RequestException:
            continue
        for row in rows:
            if row.url in resolved_seen:
                continue
            if not classify_document_candidate(row.url, row.title, row.snippet):
                continue
            resolved_seen.add(row.url)
            resolved.append(row)
            if len(resolved) >= limit:
                return resolved
    return resolved


def discover_product_documents(identity: ProductIdentity, limit: int = 8, timeout: int = 15) -> list[SearchCandidate]:
    seen: set[str] = set()
    valid: list[SearchCandidate] = []
    per_query = max(4, min(limit, 8))
    for query in build_document_queries(identity):
        for candidate in search_web_query_candidates(identity, query, limit=per_query, timeout=timeout):
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

    resolved = _resolve_valid_candidates(identity, valid, limit=limit, timeout=timeout)
    if resolved:
        return resolved

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

    return _resolve_valid_candidates(identity, fallback, limit=limit, timeout=timeout)
