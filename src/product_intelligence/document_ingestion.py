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

    The traced/automatic discovery path performs protocol-level download
    validation first. Legacy untraced callers retain the existing extract_pdf
    seam so current integrations/tests remain compatible.
    """
    source_url = url
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
        pdf_text, evidence = extract_pdf(url, "EXACT", confidence)
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
        ev.source_type = "official_pdf"

    evidence.extend(extract_target_evidence(
        pdf_text,
        target_semantics,
        source_url,
        "official_pdf",
        "EXACT",
        min(.94, accepted_confidence),
    ))
    evidence.extend(extract_text_evidence(
        pdf_text,
        source_url,
        "official_pdf",
        "EXACT",
        min(.95, accepted_confidence),
        expected_capacity=identity.capacity,
    ))

    resolved_identity = identity.model_copy(deep=True)
    resolved_identity.match_level = "EXACT"
    resolved_identity.confidence = max(float(resolved_identity.confidence or 0), float(match.confidence))
    rec = build_record_strict(resolved_identity, evidence, [source_url])
    rec.fetch = {
        **fetch_meta,
        "source_class": "official_pdf",
        "direct_document": True,
        "identity_reason": match.reason,
        "target_semantics_requested": list(target_semantics or []),
    }
    return rec
