from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import document_discovery as core_discovery
from .models import ProductIdentity
from .pdf_review import PdfInspection, PdfReviewCandidate, inspect_pdf_candidate, score_review_candidate
from .document_discovery import classify_document_candidate


@dataclass(frozen=True)
class ResolvedPdfIdentity:
    raw: ProductIdentity
    identity: ProductIdentity
    official_domain: str | None
    status: str
    confidence: float


@dataclass(frozen=True)
class ValidatedPdfCandidate:
    candidate: PdfReviewCandidate
    inspection: PdfInspection
    sha256: str
    state: str = "VALIDATED"


@dataclass(frozen=True)
class ReviewDiscoveryResult:
    resolved: ResolvedPdfIdentity
    candidates: tuple[ValidatedPdfCandidate, ...]
    discovered_count: int
    downloaded_count: int
    validated_count: int
    rejected_count: int
    duplicate_count: int


def _compact(value: str | None) -> str:
    import re
    from .normalize import key_norm

    return re.sub(r"[^a-z0-9]", "", key_norm(value or ""))


def _strong_keys(identity: ProductIdentity) -> set[str]:
    return {
        _compact(value)
        for value in (identity.mpn, identity.ean, identity.upc, identity.gtin, identity.sku)
        if value
    }


def _has_descriptive_model(identity: ProductIdentity) -> bool:
    strong = _strong_keys(identity)
    for value in (identity.model, identity.product_name):
        text = str(value or "").strip()
        if text and _compact(text) not in strong:
            return True
    return False


def _signal_dict(signal) -> dict:
    if isinstance(signal, dict):
        return dict(signal)
    return {
        "url": getattr(signal, "url", ""),
        "brand": getattr(signal, "brand", None),
        "manufacturer": getattr(signal, "manufacturer", None),
        "model": getattr(signal, "model", None),
        "product_name": getattr(signal, "product_name", None),
        "exact_raw_match": bool(getattr(signal, "exact_raw_match", False)),
        "strong_identifier_match": bool(getattr(signal, "strong_identifier_match", False)),
        "material": bool(getattr(signal, "material", False)),
        "structured_brand": bool(getattr(signal, "structured_brand", False)),
        "authority_owned": bool(getattr(signal, "authority_owned", False)),
        "reason": getattr(signal, "reason", ""),
    }


def _best_observed_model(result, original: ProductIdentity) -> str | None:
    """Recover a descriptive model from exact page probes when Excel model is the MPN."""
    strong = _strong_keys(original)
    ranked: list[tuple[int, int, str]] = []
    for raw_signal in list(getattr(result, "page_signals", []) or []):
        signal = _signal_dict(raw_signal)
        if not signal.get("material") or not signal.get("exact_raw_match"):
            continue
        for field in ("model", "product_name"):
            value = str(signal.get(field) or "").strip()
            if not value or _compact(value) in strong:
                continue
            score = 0
            score += 5 if signal.get("authority_owned") else 0
            score += 4 if signal.get("structured_brand") else 0
            score += 3 if signal.get("strong_identifier_match") else 0
            score += 2 if field == "model" else 1
            # Prefer a concise model over a full retailer product title when trust is equal.
            length_penalty = max(0, len(value) - 80) // 20
            ranked.append((score - length_penalty, -len(value), value))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    return ranked[0][2]


def _supplement_bootstrap_pages(identity: ProductIdentity, result, *, max_extra_probes: int = 4):
    """Reuse the existing identity resolver for a bounded second page-probe pass.

    The normal bootstrap intentionally probes only a few pages. If that pass learns a
    brand but leaves model==MPN, or remains unresolved, inspect a few *already found*
    candidate URLs instead of launching a second independent resolver/search system.
    """
    try:
        from .discovery import SearchCandidate
        from .identity_bootstrap import (
            PageIdentitySignal,
            _probe_candidate_page,
            resolve_identity_with_page_signals,
        )
    except Exception:
        return result

    previous_signals = []
    seen_urls: set[str] = set()
    for raw_signal in list(getattr(result, "page_signals", []) or []):
        data = _signal_dict(raw_signal)
        url = str(data.get("url") or "")
        if url:
            seen_urls.add(url)
        try:
            previous_signals.append(PageIdentitySignal(**{key: data.get(key) for key in PageIdentitySignal.__dataclass_fields__}))
        except Exception:
            pass

    candidate_urls = [str(url) for url in (getattr(result, "candidate_urls", []) or []) if str(url).strip()]
    extra_signals = []
    for url in candidate_urls:
        if url in seen_urls:
            continue
        signal = _probe_candidate_page(identity, SearchCandidate(url=url))
        extra_signals.append(signal)
        seen_urls.add(url)
        if len(extra_signals) >= max(0, int(max_extra_probes)):
            break

    if not extra_signals:
        return result

    candidates = [SearchCandidate(url=url) for url in candidate_urls]
    combined_signals = [*previous_signals, *extra_signals]
    supplemented = resolve_identity_with_page_signals(identity, candidates, combined_signals)
    supplemented.queries_executed = list(getattr(result, "queries_executed", []) or [])
    supplemented.search_results_found = int(getattr(result, "search_results_found", 0) or len(candidate_urls))
    supplemented.candidate_urls = candidate_urls
    return supplemented if supplemented.status == "RESOLVED" or getattr(result, "status", "") != "RESOLVED" else result


def resolve_pdf_identity(identity: ProductIdentity, timeout: int = 8) -> ResolvedPdfIdentity:
    """Resolve Excel code-only identity with the existing shared bootstrap.

    Strong identifiers owned by the Excel row are preserved. A second *bounded* page
    probe is allowed only when the existing bootstrap remains incomplete; it reuses
    the same page probe and resolver and does not hard-code brands or products.
    """
    if identity.brand and _has_descriptive_model(identity):
        return ResolvedPdfIdentity(
            raw=identity,
            identity=identity,
            official_domain=None,
            status="INPUT_COMPLETE",
            confidence=float(identity.confidence or 0.0),
        )

    try:
        from .identity_bootstrap import bootstrap_identity

        result = bootstrap_identity(
            identity,
            limit_per_query=14,
            timeout=max(5, min(int(timeout or 8), 8)),
        )
    except Exception:
        return ResolvedPdfIdentity(identity, identity, None, "UNRESOLVED", float(identity.confidence or 0.0))

    initial_resolved = getattr(result, "identity", None)
    incomplete = (
        str(getattr(result, "status", "")).upper() != "RESOLVED"
        or initial_resolved is None
        or not getattr(initial_resolved, "brand", None)
        or not _has_descriptive_model(initial_resolved)
    )
    if incomplete:
        result = _supplement_bootstrap_pages(identity, result, max_extra_probes=4)

    resolved = getattr(result, "identity", None)
    if str(getattr(result, "status", "")).upper() != "RESOLVED" or resolved is None:
        return ResolvedPdfIdentity(identity, identity, None, "UNRESOLVED", float(identity.confidence or 0.0))

    updates = {}
    for field in ("mpn", "ean", "upc", "gtin", "sku", "variant", "color", "region"):
        source_value = getattr(identity, field, None)
        if source_value and not getattr(resolved, field, None):
            updates[field] = source_value

    current_model = str(getattr(resolved, "model", "") or "").strip()
    if not current_model or _compact(current_model) in _strong_keys(identity):
        observed_model = _best_observed_model(result, identity)
        if observed_model:
            updates["model"] = observed_model
            product_name = str(getattr(resolved, "product_name", "") or "").strip()
            if not product_name or _compact(product_name) in _strong_keys(identity):
                updates["product_name"] = observed_model

    if updates:
        resolved = resolved.model_copy(update=updates)

    domain = str(getattr(result, "official_domain_hint", "") or "").strip() or None
    if domain is None:
        # Reuse trusted authority-owned page signals as the manufacturer-domain hint.
        from urllib.parse import urlparse

        for raw_signal in list(getattr(result, "page_signals", []) or []):
            signal = _signal_dict(raw_signal)
            if not signal.get("authority_owned") or not signal.get("exact_raw_match"):
                continue
            host = (urlparse(str(signal.get("url") or "")).hostname or "").lower().removeprefix("www.")
            if host:
                domain = host
                break

    return ResolvedPdfIdentity(
        raw=identity,
        identity=resolved,
        official_domain=domain,
        status="RESOLVED",
        confidence=float(getattr(resolved, "confidence", 0.0) or getattr(result, "confidence", 0.0) or 0.0),
    )


def discover_pdf_documents(
    identity: ProductIdentity,
    *,
    limit: int = 8,
    timeout: int = 8,
    trace=None,
):
    """Single identity-first document-discovery entry used by review and automatic modes."""
    resolved = resolve_pdf_identity(identity, timeout=timeout)
    rows = core_discovery.discover_product_documents(
        resolved.identity,
        limit=max(1, int(limit)),
        timeout=timeout,
        trace=trace,
        official_domain=resolved.official_domain,
    )
    return resolved, rows


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _review_candidate(row) -> PdfReviewCandidate:
    kind = classify_document_candidate(row.url, row.title, row.snippet) or "technical_pdf"
    provenance = getattr(row, "provenance", None)
    identity_score = int(getattr(row, "identity_score", 0) or 0)
    return PdfReviewCandidate(
        url=str(row.url),
        title=str(getattr(row, "title", "") or ""),
        snippet=str(getattr(row, "snippet", "") or ""),
        document_type=kind,
        likely_official=bool(getattr(row, "likely_official", False)),
        discovery_score=float(getattr(row, "score", 0.0) or 0.0),
        provenance=provenance,
        identity_status=str(getattr(row, "identity_status", "UNVERIFIED") or "UNVERIFIED"),
        identity_reason=str(getattr(row, "identity_reason", "") or ""),
        identity_score=identity_score,
        review_score=score_review_candidate(
            likely_official=bool(getattr(row, "likely_official", False)),
            document_type=kind,
            discovery_score=float(getattr(row, "score", 0.0) or 0.0),
            provenance=provenance,
            identity_score=identity_score,
        ),
    )


def discover_validated_review_pdfs(
    identity: ProductIdentity,
    cache_dir: str | Path,
    *,
    limit: int = 8,
    timeout: int = 10,
    log: Callable[[str], None] | None = None,
) -> ReviewDiscoveryResult:
    """Discover, download and validate PDFs before they are shown in Review PDF.

    This stage performs no OCR, no Mistral and no specification extraction. Only
    internally validated or trusted-provenance-bound PDFs are surfaced. The user's
    confirmed selection remains a separate authorization boundary.
    """
    resolved, rows = discover_pdf_documents(identity, limit=limit, timeout=timeout)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    if log:
        log(
            f"[IDENTITY] brand={resolved.identity.brand or '-'} model={resolved.identity.model or resolved.identity.product_name or '-'} "
            f"mpn={resolved.identity.mpn or '-'} status={resolved.status} domain={resolved.official_domain or '-'}"
        )

    validated: list[ValidatedPdfCandidate] = []
    rejected = 0
    duplicates = 0
    downloaded = 0
    seen_final: set[str] = set()
    seen_hashes: set[str] = set()

    for row in rows[: max(1, int(limit))]:
        candidate = _review_candidate(row)
        if log:
            log(f"[PDF CANDIDATE] {candidate.url}")
        try:
            inspection = inspect_pdf_candidate(
                resolved.identity,
                candidate.url,
                cache,
                document_type=candidate.document_type,
                likely_official=candidate.likely_official,
                discovery_score=candidate.discovery_score,
                provenance=candidate.provenance,
                identity_score=candidate.identity_score,
            )
            downloaded += 1
        except Exception as exc:
            rejected += 1
            if log:
                log(f"[DOWNLOAD/VALIDATION] REJECTED {candidate.url} · {type(exc).__name__}: {exc}")
            continue

        if not (inspection.identity_accepted or inspection.identity_provenance_bound):
            rejected += 1
            if log:
                log(f"[VALIDATION] REJECTED {candidate.url} · {inspection.identity_reason}")
            continue

        final_key = str(inspection.final_url or candidate.url).strip().lower()
        digest = sha256_file(inspection.local_path)
        if final_key in seen_final or digest in seen_hashes:
            duplicates += 1
            if log:
                log(f"[DEDUP] {candidate.url}")
            continue
        seen_final.add(final_key)
        seen_hashes.add(digest)

        surfaced = PdfReviewCandidate(
            **{
                **candidate.__dict__,
                "identity_status": "PROVENANCE_BOUND" if inspection.identity_provenance_bound else "VALIDATED",
                "identity_reason": inspection.identity_reason,
                "review_score": inspection.review_score,
            }
        )
        validated.append(ValidatedPdfCandidate(surfaced, inspection, digest))
        if log:
            log(
                f"[VALIDATION] VALIDATED url={inspection.final_url} pages={inspection.page_count} "
                f"method={'PROVENANCE' if inspection.identity_provenance_bound else 'INTERNAL'}"
            )

    validated.sort(
        key=lambda item: (
            bool(item.candidate.likely_official),
            item.inspection.identity_provenance_bound,
            item.inspection.review_score,
        ),
        reverse=True,
    )
    return ReviewDiscoveryResult(
        resolved=resolved,
        candidates=tuple(validated),
        discovered_count=len(rows),
        downloaded_count=downloaded,
        validated_count=len(validated),
        rejected_count=rejected,
        duplicate_count=duplicates,
    )
