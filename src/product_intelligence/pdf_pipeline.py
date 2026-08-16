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


def _has_descriptive_model(identity: ProductIdentity) -> bool:
    strong = {
        _compact(value)
        for value in (identity.mpn, identity.ean, identity.upc, identity.gtin, identity.sku)
        if value
    }
    for value in (identity.model, identity.product_name):
        text = str(value or "").strip()
        if text and _compact(text) not in strong:
            return True
    return False


def resolve_pdf_identity(identity: ProductIdentity, timeout: int = 8) -> ResolvedPdfIdentity:
    """Resolve Excel code-only identity with the existing shared bootstrap.

    Strong identifiers owned by the Excel row are preserved even when bootstrap
    enriches brand/model/manufacturer. No product/vendor is hard-coded here.
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

    resolved = getattr(result, "identity", None)
    if str(getattr(result, "status", "")).upper() != "RESOLVED" or resolved is None:
        return ResolvedPdfIdentity(identity, identity, None, "UNRESOLVED", float(identity.confidence or 0.0))

    updates = {}
    for field in ("mpn", "ean", "upc", "gtin", "sku", "variant", "color", "region"):
        source_value = getattr(identity, field, None)
        if source_value and not getattr(resolved, field, None):
            updates[field] = source_value
    if updates:
        resolved = resolved.model_copy(update=updates)

    domain = str(getattr(result, "official_domain_hint", "") or "").strip() or None
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

    This stage deliberately performs no OCR, no Mistral and no specification
    extraction. Only internally validated or trusted-provenance-bound PDFs are
    surfaced. The user's later confirmed selection is a separate authorization.
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

        # Discovery must finish with validated documents, not OCR-dependent guesses.
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
