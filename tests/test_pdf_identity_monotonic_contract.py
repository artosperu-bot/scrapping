from types import SimpleNamespace

from product_intelligence.identity_refinement import IdentityRefinement
from product_intelligence.models import ProductIdentity


def test_bootstrap_manufacturer_domain_is_not_overwritten_by_lower_authority_refinement(monkeypatch):
    from product_intelligence import identity_bootstrap, pdf_pipeline

    source = ProductIdentity(mpn="ZX530CBLKAM", model="ZX530CBLKAM")
    boot_identity = ProductIdentity(brand="Nova", manufacturer="Nova", model="Tune 530C", mpn="ZX530CBLKAM")

    monkeypatch.setattr(
        identity_bootstrap,
        "bootstrap_identity",
        lambda *_a, **_k: SimpleNamespace(
            status="RESOLVED", identity=boot_identity, official_domain_hint="nova.example", confidence=.97, page_signals=[]
        ),
    )
    monkeypatch.setattr(
        pdf_pipeline,
        "refine_code_identity",
        lambda *_a, **_k: IdentityRefinement(
            identity=boot_identity,
            official_domain_hint="retailer-noise.example",
            candidates_used=1,
            brand_support_domains=1,
            model_support_domains=1,
        ),
    )

    resolved = pdf_pipeline.resolve_pdf_identity(source, timeout=1)

    assert resolved.identity.brand == "Nova"
    assert resolved.identity.model == "Tune 530C"
    assert resolved.official_domain == "nova.example"


def test_sane_bootstrap_identity_is_not_replaced_by_poisoned_refinement_even_with_support(monkeypatch):
    from product_intelligence import identity_bootstrap, pdf_pipeline

    raw = "ZX530CBLKAM"
    source = ProductIdentity(mpn=raw, model=raw)
    good = ProductIdentity(brand="Nova", manufacturer="Nova", model="Tune 530C", mpn=raw)
    poisoned = ProductIdentity(brand="530CBLKAM Tune", manufacturer="530CBLKAM Tune", model="https www", mpn=raw)

    monkeypatch.setattr(
        identity_bootstrap,
        "bootstrap_identity",
        lambda *_a, **_k: SimpleNamespace(
            status="RESOLVED", identity=good, official_domain_hint="nova.example", confidence=.96, page_signals=[]
        ),
    )
    monkeypatch.setattr(
        pdf_pipeline,
        "refine_code_identity",
        lambda *_a, **_k: IdentityRefinement(
            identity=poisoned,
            official_domain_hint="noise.example",
            candidates_used=6,
            brand_support_domains=3,
            model_support_domains=3,
        ),
    )

    resolved = pdf_pipeline.resolve_pdf_identity(source, timeout=1)

    assert resolved.identity.brand == "Nova"
    assert resolved.identity.model == "Tune 530C"
    assert resolved.official_domain == "nova.example"


def test_domainless_multitoken_bootstrap_brand_can_be_repaired_by_supported_refinement(monkeypatch):
    from product_intelligence import identity_bootstrap, pdf_pipeline

    raw = "ZX530CBLKAM"
    source = ProductIdentity(mpn=raw, model=raw)
    suspicious = ProductIdentity(brand="Nova Family", manufacturer="Nova Family", model="Pulse 530C", mpn=raw)
    refined = ProductIdentity(brand="Nova", manufacturer="Nova", model="Pulse 530C", mpn=raw)

    monkeypatch.setattr(
        identity_bootstrap,
        "bootstrap_identity",
        lambda *_a, **_k: SimpleNamespace(
            status="RESOLVED", identity=suspicious, official_domain_hint=None, confidence=.96, page_signals=[]
        ),
    )
    monkeypatch.setattr(
        pdf_pipeline,
        "refine_code_identity",
        lambda *_a, **_k: IdentityRefinement(
            identity=refined,
            official_domain_hint="nova.example",
            candidates_used=6,
            brand_support_domains=3,
            model_support_domains=3,
        ),
    )

    resolved = pdf_pipeline.resolve_pdf_identity(source, timeout=1)

    assert resolved.identity.brand == "Nova"
    assert resolved.identity.manufacturer == "Nova"
    assert resolved.identity.model == "Pulse 530C"
    assert resolved.official_domain == "nova.example"
