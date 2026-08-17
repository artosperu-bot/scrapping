from product_intelligence.models import ProductIdentity


def test_refinement_does_not_choose_category_words_as_model(monkeypatch):
    from product_intelligence import identity_refinement as refinement

    original = ProductIdentity(mpn="ABC123", model="ABC123")
    current = ProductIdentity(brand="Acme", mpn="ABC123", model="ABC123")
    rows = [
        ("https://acme.com/model-350-abc123", "Acme Quantum 350 Wireless Gaming Headset ABC123", ""),
        ("https://retailer-a.example/abc123", "Acme Quantum 350 Wireless Gaming Headset ABC123", ""),
        ("https://retailer-b.example/abc123", "Acme Quantum 350 PC Gaming Headset ABC123", ""),
    ]
    monkeypatch.setattr(refinement, "_provider_search", lambda *_args, **_kwargs: rows)

    result = refinement.refine_code_identity(original, current, timeout=1, max_queries=1)

    model = (result.identity.model or "").lower()
    assert "quantum 350" in model
    assert model not in {"pc gaming", "gaming headset"}


def test_verbose_bootstrap_model_is_reduced_to_stable_product_core():
    from product_intelligence.identity_refinement import stable_model_core

    value = "JBL Tune 530C Hi-res USB-C Wired On-ear Headphones In Black - JBLT530CBLKAM"
    assert stable_model_core(value, raw="JBLT530CBLKAM", brand="JBL").lower() == "tune 530c"


def test_validated_official_pdf_can_supply_missing_official_domain(monkeypatch, tmp_path):
    from product_intelligence import live_pdf_discovery as live
    from product_intelligence.pdf_pipeline import ResolvedPdfIdentity
    from product_intelligence.pdf_review import PdfInspection

    identity = ProductIdentity(brand="Acme", model="Model 350", mpn="ABC123")
    resolved = ResolvedPdfIdentity(identity, identity, None, "RESOLVED", .95, {})
    candidate = type(
        "Row",
        (),
        {
            "url": "https://support.acme.com/files/model-350-spec.pdf",
            "title": "Acme Model 350 Spec Sheet",
            "snippet": "",
            "score": 1.0,
            "likely_official": True,
            "provenance": None,
            "identity_score": 88,
            "identity_status": "EXACT",
            "identity_reason": "exact_brand_model",
        },
    )()

    pdf = tmp_path / "spec.pdf"
    pdf.write_bytes(b"%PDF-fake")
    inspection = PdfInspection(
        candidate.url,
        candidate.url,
        pdf,
        True,
        False,
        False,
        .98,
        "brand_model",
        2,
        500,
        False,
        b"",
        95,
        True,
        None,
    )

    monkeypatch.setattr(live, "resolve_pdf_identity", lambda *_a, **_k: resolved)
    monkeypatch.setattr(live, "discover_review_product_documents", lambda *_a, **_k: [candidate])
    monkeypatch.setattr(live, "inspect_pdf_candidate", lambda *_a, **_k: inspection)
    monkeypatch.setattr(live, "sha256_file", lambda *_a, **_k: "abc")

    result = live.discover_validated_review_pdfs_live(identity, tmp_path)

    assert result.validated_count == 1
    assert result.resolved.official_domain == "support.acme.com"
