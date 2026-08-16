from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse, urlsplit, urlunsplit

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
    ("datasheet", re.compile(r"\bdata\s*sheet|\bdatasheet|\bspec\s*sheet|ficha\s+t[eé]cnica|technical\s+sheet\b", re.I)),
    ("manual", re.compile(r"\buser\s+manual|owner'?s\s+manual|manual\s+de\s+usuario|\bmanual\b", re.I)),
    ("technical_pdf", re.compile(r"\bspecifications?|technical\s+specifications?|especificaciones\b", re.I)),
)
_PROMOTIONAL = re.compile(r"\b(?:brochure|catalog(?:ue)?|promotional|buy\s+now|shop\s+now|oferta|sale)\b", re.I)
_NON_PRODUCT_PDF = re.compile(
    r"\bprivacy|privacy[_-]?policy|terms(?:[_-]?and[_-]?conditions)?|cookies?|legal|"
    r"return[_-]?policy|shipping[_-]?policy|accessibility|sitemap\b",
    re.I,
)
_GENERIC_PAGE = re.compile(r"\b(all|category|categories|catalog|catalogue|shop|store|headphones?|audifonos?|products?)\b", re.I)

MAX_QUERY_ATTEMPTS = 8
MAX_LANDING_INSPECTIONS = 8


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
        port = f":{parsed.port}" if parsed.port and not (
            (scheme == "https" and parsed.port == 443) or (scheme == "http" and parsed.port == 80)
        ) else ""
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
    return ""


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
    """Build a bounded manufacturer-first escalation ladder.

    When brand/model/domain have already been resolved, spend the limited query budget
    on official/support/document terms first. Raw-MPN-only searches remain as fallback
    for products whose manufacturer pages are poorly indexed.
    """
    brand = str(identity.brand or "").strip()
    model = _descriptive_model(identity)
    strong_values = _strong_identifiers(identity)
    domain = _clean_official_domain(official_domain)

    manufacturer_tier: list[str] = []
    if domain:
        for strong in strong_values:
            manufacturer_tier.extend([
                f'site:{domain} "{strong}"',
                f'site:{domain} "{strong}" filetype:pdf',
            ])
        if model:
            manufacturer_tier.extend([
                f'site:{domain} "{model}"',
                f'site:{domain} "{model}" filetype:pdf',
                f'site:{domain} "{model}" datasheet',
                f'site:{domain} "{model}" manual',
            ])
    if brand and model:
        manufacturer_tier.extend([
            f'"{brand}" "{model}" datasheet pdf',
            f'"{brand}" "{model}" specification sheet',
            f'"{brand}" "{model}" manual pdf',
            f'"{brand}" "{model}" support downloads',
        ])
    if brand:
        for strong in strong_values:
            manufacturer_tier.extend([
                f'"{brand}" "{strong}" specifications',
                f'"{brand}" "{strong}" filetype:pdf',
            ])

    strong_tier: list[str] = []
    for strong in strong_values:
        strong_tier.extend([
            f'"{strong}" filetype:pdf',
            f'"{strong}" datasheet',
            f'"{strong}" manual pdf',
            f'"{strong}" specifications',
            f'"{strong}" support downloads',
            f'"{strong}" pdf',
            f"{strong} pdf",
        ])

    model_tier: list[str] = []
    if brand and model:
        model_tier.extend([
            f'"{brand} {model}" specifications',
            f'"{brand} {model}" manual pdf',
            f'"{brand} {model}" datasheet pdf',
            f'"{brand}" "{model}" specifications',
        ])
    elif model:
        model_tier.extend([
            f'"{model}" datasheet pdf',
            f'"{model}" manual pdf',
        ])

    fallback_tier: list[str] = []
    fallback_tier.extend(f'"{strong}"' for strong in strong_values)
    if brand and model:
        fallback_tier.append(f'"{brand}" "{model}"')

    tiers = []
    for tier in (manufacturer_tier, strong_tier, model_tier, fallback_tier):
        unique = list(dict.fromkeys(query.strip() for query in tier if query.strip()))
        if unique:
            tiers.append(unique)
    return tiers


def build_document_queries(identity: ProductIdentity, official_domain: str | None = None) -> list[str]:
    return [query for tier in build_document_query_tiers(identity, official_domain=official_domain) for query in tier]


def _model_tokens(value: str) -> tuple[list[str], list[str]]:
    tokens = re.findall(r"[a-z]+|\d+", key_norm(value or ""))
    words = [
        token
        for token in tokens
        if token.isalpha()
        and len(token) >= 3
        and token not in {"wireless", "wired", "gaming", "headset", "headphone", "headphones"}
    ]
    numbers = [token for token in tokens if token.isdigit() and len(token) >= 1]
    return words, numbers


def assess_document_candidate(identity: ProductIdentity, url: str, title: str = "", snippet: str = "") -> DocumentCandidateAssessment:
    """Assess metadata without trusting search-engine query echo in snippets."""
    primary = f"{url} {title}"
    primary_compact = _compact(primary)
    primary_norm = key_norm(primary)
    snippet_compact = _compact(snippet)
    strong_values = [_compact(x) for x in _strong_identifiers(identity)]

    exact_strong = any(value and value in primary_compact for value in strong_values)
    if exact_strong:
        return DocumentCandidateAssessment(True, "exact_strong_identifier", 100, exact_strong_id=True)

    brand = _compact(identity.brand)
    model_text = _descriptive_model(identity)
    model = _compact(model_text)
    exact_model = bool(model and model in primary_compact and (not brand or brand in primary_compact))
    if exact_model:
        return DocumentCandidateAssessment(True, "exact_brand_model", 88, exact_model=True)

    if any(value and value in snippet_compact for value in strong_values):
        return DocumentCandidateAssessment(False, "snippet_only_strong_identifier", 0)

    if brand and brand in primary_compact:
        words, requested_numbers = _model_tokens(model_text)
        candidate_numbers = set(re.findall(r"\b\d{1,4}\b", primary_norm))
        has_requested_family = any(word in primary_norm for word in words) if words else False
        if requested_numbers and has_requested_family and not any(number in candidate_numbers for number in requested_numbers):
            return DocumentCandidateAssessment(False, "sibling_model_conflict", 0, conflict=True)
        if classify_document_candidate(url, title, "") and model and model not in primary_compact:
            return DocumentCandidateAssessment(False, "sibling_model_conflict", 0, conflict=True)
        if _GENERIC_PAGE.search(title):
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
    if str(provenance.parent_authority).upper() != "MANUFACTURER":
        return False
    if float(provenance.parent_identity_confidence or 0.0) < 0.85:
        return False
    if str(internal_identity_reason or "") in {
        "strong_identifier_conflict",
        "sibling_model_url_conflict",
        "identity_conflict",
    }:
        return False
    return str(internal_identity_reason or "") in {"strong_identifier_missing", "identity_not_confirmed"}


def _normalize_document_words(value: str) -> str:
    text = unquote(str(value or ""))
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"[_/\\+.-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _document_semantic_text(url: str, title: str = "", snippet: str = "") -> str:
    return _normalize_document_words(f"{url} {title} {snippet}")


def _promotion_semantic_text(url: str, title: str = "") -> str:
    decoded = unquote(str(url or ""))
    try:
        filename = urlparse(decoded).path.rsplit("/", 1)[-1]
    except Exception:
        filename = decoded
    return _normalize_document_words(f"{filename} {title}")


def classify_document_candidate(url: str, title: str = "", snippet: str = "") -> str | None:
    text = _document_semantic_text(url, title, snippet)
    if _PROMOTIONAL.search(_promotion_semantic_text(url, title)):
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

# Remaining resolver/search pipeline continues unchanged below this point.
