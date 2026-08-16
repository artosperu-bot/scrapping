from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

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
) -> ProductRecord:
    """Validate and ingest one PDF without allowing HTML into evidence.

    Directly discovered PDFs are treated as technical documents, not automatically as
    manufacturer-owned documents. Exact document identity is still mandatory.
    """
    source_url = url
    focus_terms = _pdf_focus_terms(identity, target_semantics)
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
                )
        downloaded = download_pdf(url, Path(download_dir), timeout=35, trace=trace)
        source_url = downloaded.final_url
        pdf_text, evidence = extract_pdf_bytes(
            downloaded.path.read_bytes(),
            downloaded.final_url,
            "EXACT",
            confidence,
            focus_terms=focus_terms,
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
    if not match.accepted:
        if trace:
            trace.emit("PDF_DOWNLOAD_REJECTED", url=source_url, reason=f"IDENTITY:{match.reason}")
        raise ValueError(f"PDF rechazado por identidad: {match.reason}")

    accepted_confidence = min(float(confidence), float(match.confidence))
    for ev in evidence:
        ev.match_level = "EXACT"
        ev.confidence = min(float(ev.confidence or accepted_confidence), accepted_confidence)
        ev.source_type = "technical_pdf"

    evidence.extend(extract_target_evidence(
        pdf_text,
        target_semantics,
        source_url,
        "technical_pdf",
        "EXACT",
        min(.94, accepted_confidence),
    ))
    evidence.extend(extract_text_evidence(
        pdf_text,
        source_url,
        "technical_pdf",
        "EXACT",
        min(.95, accepted_confidence),
        expected_capacity=identity.capacity,
    ))

    policy_accepted = []
    policy_rejected = []
    for ev in evidence:
        decision = decide_evidence(
            page_type="DOCUMENT",
            identity_status="EXACT",
            source_class="technical_document",
            extraction_method="pdf_native",
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
    resolved_identity.confidence = max(float(resolved_identity.confidence or 0), float(match.confidence))
    rec = build_record_strict(resolved_identity, policy_accepted, [source_url])
    source_decision = {
        "page_type": "DOCUMENT",
        "page_type_confidence": 1.0,
        "page_type_reasons": ["PDF_PROTOCOL_VALIDATED"],
        "material_allowed": True,
        "identity": "EXACT",
        "identity_confidence": float(match.confidence),
        "identity_reasons": [match.reason],
        "identity_matched": [],
        "identity_conflicts": [],
        "authority": "technical_document",
        "authority_confidence": 0.70,
        "authority_reasons": ["DIRECT_DOCUMENT_NO_OWNERSHIP_ASSUMPTION"],
    }
    rec.fetch = {
        **fetch_meta,
        "source_class": "technical_document",
        "source_decision": source_decision,
        "direct_document": True,
        "identity_reason": match.reason,
        "target_semantics_requested": list(target_semantics or []),
        "pdf_focus_terms": focus_terms,
    }
    rec.evidence_graph = dict(rec.evidence_graph or {})
    rec.evidence_graph["source_decision"] = source_decision
    rec.evidence_graph["source_validation_counts"] = {
        "policy_evidence_accepted": len(policy_accepted),
        "policy_evidence_rejected": len(policy_rejected),
    }
    if policy_rejected:
        existing = list(rec.evidence_graph.get("rejected_evidence") or [])
        rec.evidence_graph["rejected_evidence"] = (existing + policy_rejected)[:500]
    return rec
