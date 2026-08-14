from __future__ import annotations

from .models import ProductIdentity, ProductRecord
from .pdf_evidence import validate_pdf_identity
from .pdf_extract import extract_pdf
from .record_builder import build_record_strict
from .target_extract import extract_target_evidence
from .text_extract import extract_text_evidence


def process_pdf_document(
    identity: ProductIdentity,
    url: str,
    *,
    target_semantics: list[str] | None = None,
    confidence: float = .95,
) -> ProductRecord:
    """Validate and ingest a discovered PDF without bypassing the normal evidence pool."""
    pdf_text, evidence = extract_pdf(url, "EXACT", confidence)
    match = validate_pdf_identity(identity, pdf_text, url)
    if not match.accepted:
        raise ValueError(f"PDF rechazado por identidad: {match.reason}")

    accepted_confidence = min(float(confidence), float(match.confidence))
    for ev in evidence:
        ev.match_level = "EXACT"
        ev.confidence = min(float(ev.confidence or accepted_confidence), accepted_confidence)
        ev.source_type = "official_pdf"

    evidence.extend(extract_target_evidence(
        pdf_text,
        target_semantics,
        url,
        "official_pdf",
        "EXACT",
        min(.94, accepted_confidence),
    ))
    evidence.extend(extract_text_evidence(
        pdf_text,
        url,
        "official_pdf",
        "EXACT",
        min(.95, accepted_confidence),
        expected_capacity=identity.capacity,
    ))

    resolved_identity = identity.model_copy(deep=True)
    resolved_identity.match_level = "EXACT"
    resolved_identity.confidence = max(float(resolved_identity.confidence or 0), float(match.confidence))
    rec = build_record_strict(resolved_identity, evidence, [url])
    rec.fetch = {
        "method": "direct_pdf",
        "status_code": 200,
        "final_url": url,
        "source_class": "official_pdf",
        "direct_document": True,
        "identity_reason": match.reason,
        "target_semantics_requested": list(target_semantics or []),
    }
    return rec
