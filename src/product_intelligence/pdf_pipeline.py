from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import document_discovery as core_discovery
from .document_discovery import classify_document_candidate
from .identity_refinement import refine_code_identity
from .models import ProductIdentity
from .normalize import key_norm
from .pdf_review import PdfInspection, PdfReviewCandidate, inspect_pdf_candidate, score_review_candidate


@dataclass(frozen=True)
class ResolvedPdfIdentity:
    raw: ProductIdentity
    identity: ProductIdentity
    official_domain: str | None
    status: str
    confidence: float
    diagnostics: dict = field(default_factory=dict)


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
    return re.sub(r"[^a-z0-9]", "", key_norm(value or ""))


def _strong_keys(identity: ProductIdentity) -> set[str]:
    return {
        _compact(value)
        for value in (identity.mpn, identity.ean, identity.upc, identity.gtin, identity.sku)
        if value
    }


def _input_is_code_only(identity: ProductIdentity) -> bool:
    strong = _strong_keys(identity)
    model = _compact(identity.model)
    product_name = _compact(identity.product_name)
    return bool(strong and ((model and model in strong) or (product_name and product_name in strong)))


def _has_descriptive_model(identity: ProductIdentity) -> bool:
    strong = _strong_keys(identity)
    for value in (identity.model, identity.product_name):
        text = str(value or "").strip()
        if text and _compact(text) not in strong and len(text) <= 100:
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
    }


def _best_observed_model(result, original: ProductIdentity) -> str | None:
    strong = _strong_keys(original)
    ranked: list[tuple[int, int, str]] = []
    for raw_signal in list(getattr(result, "page_signals", []) or []):
        signal = _signal_dict(raw_signal)
        if not signal.get("material") or not signal.get("exact_raw_match"):
            continue
        for field_name in ("model", "product_name"):
            value = str(signal.get(field_name) or "").strip()
            if not value or _compact(value) in strong or len(value) > 100:
                continue
            score = 0
            score += 8 if signal.get("authority_owned") else 0
            score += 5 if signal.get("structured_brand") else 0
            score += 4 if signal.get("strong_identifier_match") else 0
            score += 2 if field_name == "model" else 0
            ranked.append((score, -len(value), value))
    return max(ranked)[2] if ranked else None


def _preserve_excel_identifiers(original: ProductIdentity, resolved: ProductIdentity) -> ProductIdentity:
    updates = {}
    for name in ("mpn", "ean", "upc", "gtin", "sku", "variant", "color", "region"):
        source = getattr(original, name, None)
        if source and not getattr(resolved, name, None):
            updates[name] = source
    return resolved.model_copy(update=updates) if updates else resolved


def resolve_pdf_identity(identity: ProductIdentity, timeout: int = 8) -> ResolvedPdfIdentity:
    """Resolve the real Excel identity before any PDF query.

    Existing bootstrap remains the first resolver. Code-only Excel rows are always
    cross-checked by a bounded, cross-domain consensus pass because a bootstrap result
    such as `brand=Acme, model=<MPN>` or a retailer marketing title is not enough for
    manufacturer-first document discovery. No brand/product is hard-coded.
    """
    code_only_input = _input_is_code_only(identity)
    if identity.brand and _has_descriptive_model(identity) and not code_only_input:
        return ResolvedPdfIdentity(
            identity,
            identity,
            None,
            "INPUT_COMPLETE",
            float(identity.confidence or 0.0),
            {"input_code_only": False, "refinement_used": False},
        )

    try:
        from .identity_bootstrap import bootstrap_identity
        bootstrap = bootstrap_identity(
            identity,
            limit_per_query=14,
            timeout=max(5, min(int(timeout or 8), 8)),
        )
    except Exception as exc:
        bootstrap = None
        bootstrap_error = f"{type(exc).__name__}: {exc}"
    else:
        bootstrap_error = None

    bootstrap_status = str(getattr(bootstrap, "status", "")).upper() if bootstrap is not None else ""
    base = getattr(bootstrap, "identity", None) if bootstrap_status == "RESOLVED" else None
    base = _preserve_excel_identifiers(identity, base or identity)

    observed_model = _best_observed_model(bootstrap, identity) if bootstrap is not None else None
    if observed_model and not _has_descriptive_model(base):
        base = base.model_copy(update={"model": observed_model, "product_name": observed_model})

    bootstrap_domain = str(getattr(bootstrap, "official_domain_hint", "") or "").strip() or None
    suspicious_brand = bool(base.brand and len(str(base.brand).split()) > 1 and not bootstrap_domain)
    suspicious_model = bool(
        not _has_descriptive_model(base)
        or len(str(base.model or base.product_name or "")) > 70
        or (_compact(identity.mpn) and _compact(identity.mpn) in _compact(base.model or ""))
    )
    needs_refinement = code_only_input or not base.brand or suspicious_brand or suspicious_model

    refined_domain = None
    refinement_diag = {
        "input_code_only": code_only_input,
        "bootstrap_status": bootstrap_status or "UNAVAILABLE",
        "bootstrap_brand": base.brand,
        "bootstrap_model": base.model or base.product_name,
        "bootstrap_domain": bootstrap_domain,
        "bootstrap_error": bootstrap_error,
        "refinement_used": needs_refinement,
    }

    if needs_refinement:
        try:
            refined = refine_code_identity(
                identity,
                base,
                timeout=max(5, min(int(timeout or 8), 8)),
                max_queries=2,
            )
            refinement_diag.update({
                "refinement_candidates": refined.candidates_used,
                "brand_support_domains": refined.brand_support_domains,
                "model_support_domains": refined.model_support_domains,
                "refined_brand": refined.identity.brand,
                "refined_model": refined.identity.model or refined.identity.product_name,
                "refined_domain": refined.official_domain_hint,
            })
            # A cross-domain model consensus is valuable even if bootstrap already had
            # a brand. Brand replacement itself remains stricter.
            updates = {}
            if refined.brand_support_domains >= 2 and refined.identity.brand:
                updates["brand"] = refined.identity.brand
                if refined.identity.manufacturer:
                    updates["manufacturer"] = refined.identity.manufacturer
            if refined.model_support_domains >= 2 and refined.identity.model:
                updates["model"] = refined.identity.model
                updates["product_name"] = refined.identity.product_name or refined.identity.model
            if updates:
                base = base.model_copy(update=updates)
            refined_domain = refined.official_domain_hint
        except Exception as exc:
            refinement_diag["refinement_error"] = f"{type(exc).__name__}: {exc}"

    base = _preserve_excel_identifiers(identity, base)
    resolved_enough = bool(base.brand and _has_descriptive_model(base))
    return ResolvedPdfIdentity(
        raw=identity,
        identity=base,
        official_domain=refined_domain or bootstrap_domain,
        status="RESOLVED" if resolved_enough else "PARTIAL_IDENTITY",
        confidence=float(getattr(base, "confidence", 0.0) or getattr(bootstrap, "confidence", 0.0) or 0.0),
        diagnostics=refinement_diag,
    )


def discover_pdf_documents(identity: ProductIdentity, *, limit: int = 8, timeout: int = 8, trace=None):
    """Shared identity-first document discovery for both REVIEWED and AUTOMATIC modes."""
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
    """Resolve -> discover -> download -> validate -> dedupe; never OCR/Mistral here."""
    resolved, rows = discover_pdf_documents(identity, limit=limit, timeout=timeout)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    if log:
        log(
            f"[IDENTITY] brand={resolved.identity.brand or '-'} model={resolved.identity.model or resolved.identity.product_name or '-'} "
            f"mpn={resolved.identity.mpn or '-'} status={resolved.status} domain={resolved.official_domain or '-'}"
        )
        log(f"[IDENTITY DIAGNOSTICS] {resolved.diagnostics}")

    validated: list[ValidatedPdfCandidate] = []
    rejected = 0
    duplicates = 0
    downloaded = 0
    seen_final: set[str] = set()
    seen_hashes: set[str] = set()

    for row in rows[: max(1, int(limit))]:
        candidate = _review_candidate(row)
        if log:
            log(f"[PDF CANDIDATE] {candidate.url} · title={candidate.title} · provenance={candidate.provenance}")
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
                log(f"[VALIDATION] REJECTED {candidate.url} · {inspection.identity_reason} · pages={inspection.page_count}")
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
