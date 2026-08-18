from __future__ import annotations

from types import SimpleNamespace

from product_intelligence import identity_bootstrap
from product_intelligence import pdf_pipeline
from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_evidence import validate_pdf_identity
from product_intelligence.product_document_matcher import SIBLING_VARIANT


def test_refinement_cannot_drop_proven_wireless_discriminator(monkeypatch):
    original = ProductIdentity(
        mpn="ACMERUN3BTBAM",
        model="ACMERUN3BTBAM",
        product_name="ACMERUN3BTBAM",
    )
    descriptive = (
        "Acme Run 3 Waterproof Wireless Sports In-Ear Headphones "
        "with Secure Training Fit - Blue"
    )
    bootstrap_identity = ProductIdentity(
        brand="Acme",
        manufacturer="Acme",
        model=descriptive,
        product_name=descriptive,
        confidence=0.91,
    )
    refined_identity = ProductIdentity(
        brand="Acme",
        manufacturer="Acme",
        model="Acme Run 3",
        product_name="Acme Run 3",
        confidence=0.95,
    )

    monkeypatch.setattr(
        identity_bootstrap,
        "bootstrap_identity",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="RESOLVED",
            identity=bootstrap_identity,
            official_domain_hint=None,
            page_signals=[],
        ),
    )
    monkeypatch.setattr(
        pdf_pipeline,
        "refine_code_identity",
        lambda *_args, **_kwargs: SimpleNamespace(
            identity=refined_identity,
            candidates_used=4,
            brand_support_domains=4,
            model_support_domains=4,
            official_domain_hint="acme.example",
        ),
    )

    resolved = pdf_pipeline.resolve_pdf_identity(original, timeout=1)
    target_text = " ".join(
        str(value or "")
        for value in (resolved.identity.model, resolved.identity.product_name, resolved.identity.variant)
    ).lower()

    # Monotonic identity: shortening the canonical model may be useful, but a
    # discriminating functional variant already demonstrated by stronger earlier
    # evidence must survive refinement.
    assert "wireless" in target_text

    sibling = validate_pdf_identity(
        resolved.identity,
        "Acme Run 3 Wired Sport Headphones. Product specification.",
        "https://acme.example/run-3-wired-specsheet.pdf",
    )
    assert sibling.accepted is False
    assert sibling.relationship == SIBLING_VARIANT
    assert any("wireless" in conflict.lower() and "wired" in conflict.lower() for conflict in sibling.hard_conflicts)


def test_existing_explicit_variant_remains_authoritative(monkeypatch):
    original = ProductIdentity(
        brand="Acme",
        mpn="ACMERUN3BTBAM",
        model="Acme Run 3",
        product_name="Acme Run 3",
        variant="Wireless",
        confidence=0.99,
    )

    # Complete user/Excel identity should not need web refinement and must preserve
    # its explicit variant all the way into the document matcher.
    resolved = pdf_pipeline.resolve_pdf_identity(original, timeout=1)
    assert resolved.identity.variant == "Wireless"

    sibling = validate_pdf_identity(
        resolved.identity,
        "Acme Run 3 Wired Sport Headphones",
        "https://acme.example/run-3-wired.pdf",
    )
    assert sibling.accepted is False
    assert sibling.relationship == SIBLING_VARIANT
