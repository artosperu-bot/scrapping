from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from .document_discovery import DocumentProvenance, can_bind_document_by_provenance
from .models import ProductIdentity, ProductRecord
from .pdf_download import download_pdf
from .pdf_evidence import validate_pdf_identity
from .pdf_extract import extract_pdf, extract_pdf_bytes
from .record_builder import build_record_strict
from .target_extract import extract_target_evidence
from .text_extract import extract_text_evidence
from .evidence_policy import decide_evidence


def _pdf_focus_terms(identity: ProductIdentity, target_semantics: list[str] | None) -> list[str]:
    values = [
        identity.model,
        identity.product_name,
        identity.mpn,
        identity.ean,
        identity.upc,
        identity.gtin,
        *(target_semantics or []),
    ]
    return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def process_pdf_document(
    identity: ProductIdentity,
    url: str,
    *,
    target_semantics: list[str] | None = None,
    confidence: float = .95,
    trace=None,
    download_dir: str | Path | None = None,
    provenance: DocumentProvenance | None = None,
) -> ProductRecord:
    """Validate and ingest one PDF without allowing HTML into evidence.

    A directly discovered PDF must prove identity on its own. A user-approved PDF
    linked directly from an EXACT validated parent may use that provenance only when
    the PDF has no conflicting identity. Provenance never overrides a conflict.
    """
    source_url = url
    focus_terms = _pdf_focus_terms(identity, target_semantics)
    parent_url = provenance.parent_url if provenance else None
    fetch_meta = {
        "method": "direct_pdf",
        "status_code": 200,
        "final_url": url,
        "source_url": url,
        "content_type": None,
        "size_bytes": None,
        "sha256": None,
    }

    if trace is None and download_dir is None:
        pdf_text, evidence = extract_pdf(
            url,
            "EXACT",
            confidence,
            focus_terms=focus_terms,
            parent_source_url=parent_url,
        )
    else:
        if download_dir is None:
            with TemporaryDirectory(prefix="product-intelligence-pdf-") as tmp:
                return process_pdf_document(
                    identity,
                    url,
                    target_semantics=target_semantics,
                    confidence=confidence,
                    trace=trace,
                    download_dir=Path(tmp),
                    provenance=provenance,
                )
        downloaded = download_pdf(url, Path(download_dir), timeout=35, trace=trace)
        source_url = downloaded.final_url
        pdf_text, evidence = extract_pdf_bytes(
            downloaded.path.read_bytes(),
            downloaded.final_url,
            "EXACT",
            confidence,
            focus_terms=focus_terms,
            parent_source_url=parent_url,
        )
        fetch_meta.update({
            "method": "downloaded_pdf",
            "final_url": downloaded.final_url,
            "source_url": downloaded.source_url,
            "content_type": downloaded.content_type,
            "size_bytes": downloaded.size_bytes,
            "sha256": downloaded.sha256,
        })

    match = validate_pdf_identity(identity, pdf_text, source_url)
    provenance_bound = False
    if not match.accepted:
        provenance_bound = can_bind_document_by_provenance(
            provenance,
            internal_identity_reason=str(match.reason),
        )
        if not provenance_bound:
            if trace:
                trace.emit("PDF_DOWNLOAD_REJECTED", url=source_url, reason=f"IDENTITY:{match.reason}")
            raise ValueError(f"PDF rechazado por identidad: {match.reason}")
        if trace:
            trace.emit("PDF_PROVENANCE_BOUND", url=source_url, parent_url=parent_url)

    identity_reason = "identity_bound_by_provenance" if provenance_bound else str(match.reason)
    identity_confidence = (
        min(.96, float(provenance.parent_identity_confidence) * .95)
        if provenance_bound and provenance is not None
        else float(match.confidence)
    )
    accepted_confidence = min(float(confidence), identity_confidence)
    for ev in evidence:
        ev.match_level = "EXACT"
        ev.confidence = min(float(ev.confidence or accepted_confidence), accepted_confidence)
        ev.source_type = "technical_pdf"
        if parent_url and not ev.parent_source_url:
            ev.parent_source_url = parent_url
        if ev.extraction_method is None and ev.selector and "method=" in ev.selector:
            ev.extraction_method = ev.selector.split("method=", 1)[1].split()[0]
        if ev.raw_snippet is None and ev.raw_value is not None:
            ev.raw_snippet = f"{ev.attribute}: {ev.raw_value}"[:500]

    target_evidence = extract_target_evidence(
        pdf_text,
        target_semantics,
        source_url,
        "technical_pdf",
        "EXACT",
        min(.94, accepted_confidence),
    )
    text_evidence = extract_text_evidence(
        pdf_text,
        source_url,
        "technical_pdf",
        "EXACT",
        min(.95, accepted_confidence),
        expected_capacity=identity.capacity,
    )
    for ev in [*target_evidence, *text_evidence]:
        if parent_url:
            ev.parent_source_url = parent_url
        if ev.raw_snippet is None and ev.raw_value is not None:
            ev.raw_snippet = f"{ev.attribute}: {ev.raw_value}"[:500]
    evidence.extend(target_evidence)
    evidence.extend(text_evidence)

    policy_accepted = []
    policy_rejected = []
    for ev in evidence:
        extraction_method = "pdf_ocr" if str(ev.extraction_method or "").upper() == "OCR" else "pdf_native"
        decision = decide_evidence(
            page_type="DOCUMENT",
            identity_status="EXACT",
            source_class="technical_document",
            extraction_method=extraction_method,
            semantic=ev.attribute,
            confidence=float(ev.confidence or 0.0),
        )
        if decision.allowed:
            policy_accepted.append(ev)
        else:
            policy_rejected.append({
                "attribute": ev.attribute,
                "value": ev.raw_value,
                "source": ev.source_url,
                "reason": decision.reason,
            })

    resolved_identity = identity.model_copy(deep=True)
    resolved_identity.match_level = "EXACT"
    resolved_identity.confidence = max(float(resolved_identity.confidence or 0), identity_confidence)
    rec = build_record_strict(resolved_identity, policy_accepted, [source_url])
    authority = (
        str(provenance.parent_authority).lower()
        if provenance_bound and provenance is not None
        else "technical_document"
    )
    source_decision = {
        "page_type": "DOCUMENT",
        "page_type_confidence": 1.0,
        "page_type_reasons": ["PDF_PROTOCOL_VALIDATED"],
        "material_allowed": True,
        "identity": "EXACT",
        "identity_confidence": identity_confidence,
        "identity_reasons": [identity_reason],
        "identity_matched": [],
        "identity_conflicts": [],
        "authority": authority,
        "authority_confidence": 0.90 if provenance_bound else 0.70,
        "authority_reasons": ["EXACT_PARENT_PROVENANCE"] if provenance_bound else ["DIRECT_DOCUMENT_NO_OWNERSHIP_ASSUMPTION"],
    }
    rec.fetch = {
        **fetch_meta,
        "source_class": "technical_document",
        "source_decision": source_decision,
        "direct_document": True,
        "identity_reason": identity_reason,
        "target_semantics_requested": list(target_semantics or []),
        "pdf_focus_terms": focus_terms,
        "document_provenance": asdict(provenance) if provenance else None,
        "provenance_bound": provenance_bound,
    }
    rec.evidence_graph = dict(rec.evidence_graph or {})
    rec.evidence_graph["source_decision"] = source_decision
    rec.evidence_graph["source_validation_counts"] = {
        "policy_evidence_accepted": len(policy_accepted),
        "policy_evidence_rejected": len(policy_rejected),
    }
    if provenance:
        rec.evidence_graph["document_provenance"] = asdict(provenance)
    if policy_rejected:
        existing = list(rec.evidence_graph.get("rejected_evidence") or [])
        rec.evidence_graph["rejected_evidence"] = (existing + policy_rejected)[:500]
    return rec