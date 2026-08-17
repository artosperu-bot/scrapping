from __future__ import annotations

from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .models import ProductIdentity
from .pdf_pipeline import (
    ResolvedPdfIdentity,
    ReviewDiscoveryResult,
    ValidatedPdfCandidate,
    _review_candidate,
    resolve_pdf_identity,
    sha256_file,
)
from .pdf_review import PdfReviewCandidate, inspect_pdf_candidate
from .pdf_review_search_strategy import discover_review_product_documents
from .pdf_search_trace import PdfSearchTrace, format_trace_lines


def discover_validated_review_pdfs_live(
    identity: ProductIdentity,
    cache_dir: str | Path,
    *,
    limit: int = 8,
    timeout: int = 10,
    log: Callable[[str], None] | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> ReviewDiscoveryResult:
    """Live review discovery: identity -> PDP/PDF search -> download/validation; no OCR/Mistral."""

    def emit(event_type: str, **payload):
        if on_event:
            on_event({"type": event_type, **payload})

    class LiveTrace(PdfSearchTrace):
        def emit(self, event: str, **data) -> None:
            super().emit(event, **data)
            if event == "PDF_PDP_SEARCH":
                emit("pdp", stage="PDP_SEARCH", status="SEARCHING", **data)
            elif event == "PDF_PDP_VALIDATED":
                emit("pdp", stage="PDP_VALIDATED", status="VALIDATED", **data)
            elif event == "PDF_LINK_DISCOVERED":
                emit("document", stage="DOCUMENT_FOUND", status="FOUND", **data)
            elif event == "PDF_PROVENANCE_BOUND":
                emit("document", stage="PROVENANCE_BOUND", status="VALIDATED", **data)

    emit("stage", stage="IDENTITY", message="Resolviendo identidad…")
    resolved = resolve_pdf_identity(identity, timeout=timeout)
    trace = LiveTrace(str(resolved.identity.mpn or resolved.identity.ean or resolved.identity.upc or resolved.identity.gtin or resolved.identity.model or "product"))
    rows = [] if resolved.status == "CONFLICT" else discover_review_product_documents(
        resolved.identity,
        limit=limit,
        timeout=timeout,
        official_domain=resolved.official_domain,
        trace=trace,
    )
    emit(
        "identity",
        stage="SEARCH",
        brand=resolved.identity.brand,
        model=resolved.identity.model or resolved.identity.product_name,
        status=resolved.status,
        official_domain=resolved.official_domain,
        discovered=len(rows),
    )

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    if log:
        log(
            f"[IDENTITY] brand={resolved.identity.brand or '-'} model={resolved.identity.model or resolved.identity.product_name or '-'} "
            f"mpn={resolved.identity.mpn or '-'} status={resolved.status} domain={resolved.official_domain or '-'}"
        )
        log(f"[IDENTITY DIAGNOSTICS] {resolved.diagnostics}")
        for line in format_trace_lines(trace):
            log(line)

    validated: list[ValidatedPdfCandidate] = []
    rejected = 0
    duplicates = 0
    downloaded = 0
    seen_final: set[str] = set()
    seen_hashes: set[str] = set()

    for position, source_row in enumerate(rows[: max(1, int(limit))], 1):
        candidate = _review_candidate(source_row)
        emit(
            "candidate",
            stage="VALIDATE",
            position=position,
            total=min(len(rows), max(1, int(limit))),
            candidate=candidate,
            url=candidate.url,
            title=candidate.title,
        )
        if log:
            log(f"[PDF CANDIDATE] {candidate.url} · title={candidate.title} · provenance={candidate.provenance}")
        try:
            emit("download", stage="DOWNLOAD", status="STARTED", url=candidate.url)
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
            emit("download", stage="VALIDATE", status="FINISHED", url=candidate.url)
        except Exception as exc:
            rejected += 1
            error = f"{type(exc).__name__}: {exc}"
            emit("rejected", stage="VALIDATE", url=candidate.url, reason="DOWNLOAD_OR_VALIDATION", error=error)
            if log:
                log(f"[DOWNLOAD/VALIDATION] REJECTED {candidate.url} · {error}")
            continue

        if not (inspection.identity_accepted or inspection.identity_provenance_bound):
            rejected += 1
            emit(
                "rejected",
                stage="VALIDATE",
                url=candidate.url,
                reason=inspection.identity_reason or "IDENTITY",
                pages=inspection.page_count,
            )
            if log:
                log(f"[VALIDATION] REJECTED {candidate.url} · {inspection.identity_reason} · pages={inspection.page_count}")
            continue

        final_key = str(inspection.final_url or candidate.url).strip().lower()
        digest = sha256_file(inspection.local_path)
        if final_key in seen_final or digest in seen_hashes:
            duplicates += 1
            emit("duplicate", stage="VALIDATE", url=candidate.url, final_url=inspection.final_url)
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
        row = ValidatedPdfCandidate(surfaced, inspection, digest)
        validated.append(row)
        emit("validated", stage="VALIDATE", row=row, url=surfaced.url, pages=inspection.page_count)
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

    if not resolved.official_domain:
        learned_host = ""
        for item in validated:
            if not item.candidate.likely_official:
                continue
            learned_host = (
                urlparse(str(item.inspection.final_url or item.candidate.url)).hostname or ""
            ).lower().removeprefix("www.")
            if learned_host:
                break
        if learned_host:
            diagnostics = dict(resolved.diagnostics or {})
            diagnostics["official_domain_source"] = "VALIDATED_OFFICIAL_PDF"
            resolved = ResolvedPdfIdentity(
                raw=resolved.raw,
                identity=resolved.identity,
                official_domain=learned_host,
                status=resolved.status,
                confidence=resolved.confidence,
                diagnostics=diagnostics,
            )
            emit("authority", stage="VALIDATE", status="LEARNED", official_domain=learned_host)
            if log:
                log(f"[AUTHORITY] learned official_domain={learned_host} from validated PDF")

    result = ReviewDiscoveryResult(
        resolved=resolved,
        candidates=tuple(validated),
        discovered_count=len(rows),
        downloaded_count=downloaded,
        validated_count=len(validated),
        rejected_count=rejected,
        duplicate_count=duplicates,
    )
    emit(
        "done",
        stage="DONE",
        discovered=result.discovered_count,
        downloaded=result.downloaded_count,
        validated=result.validated_count,
        rejected=result.rejected_count,
        duplicates=result.duplicate_count,
    )
    return result
