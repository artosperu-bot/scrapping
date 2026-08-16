from pathlib import Path
from types import SimpleNamespace

from product_intelligence.models import ProductIdentity


def test_shared_pdf_discovery_bootstraps_mpn_only_before_queries(monkeypatch):
    from product_intelligence import pdf_pipeline
    from product_intelligence import identity_bootstrap

    source = ProductIdentity(mpn="ABC123", model="ABC123")
    enriched = ProductIdentity(mpn="ABC123", brand="Acme", model="Model X")
    monkeypatch.setattr(
        identity_bootstrap,
        "bootstrap_identity",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="RESOLVED",
            identity=enriched,
            official_domain_hint="acme.example",
        ),
    )

    captured = {}
    monkeypatch.setattr(
        pdf_pipeline.core_discovery,
        "discover_product_documents",
        lambda identity, **kwargs: captured.update(identity=identity, kwargs=kwargs) or [],
    )

    resolved, rows = pdf_pipeline.discover_pdf_documents(source, limit=3, timeout=8)
    assert rows == []
    assert resolved.identity.brand == "Acme"
    assert resolved.identity.model == "Model X"
    assert resolved.identity.mpn == "ABC123"
    assert captured["identity"].brand == "Acme"
    assert captured["kwargs"]["official_domain"] == "acme.example"


def test_review_service_downloads_validates_and_deduplicates_before_surface(monkeypatch, tmp_path):
    from product_intelligence import pdf_pipeline as service

    identity = ProductIdentity(mpn="ABC123", brand="Acme", model="Model X")
    resolved = service.ResolvedPdfIdentity(identity, identity, "acme.example", "INPUT_COMPLETE", .95)
    rows = [
        SimpleNamespace(url="https://acme.example/spec.pdf", title="Model X Specification Sheet", snippet="", score=1.0, likely_official=True, provenance=None, identity_score=100, identity_status="EXACT", identity_reason="exact_model"),
        SimpleNamespace(url="https://cdn.acme.example/copy.pdf", title="Model X Specification Sheet", snippet="", score=.9, likely_official=True, provenance=None, identity_score=100, identity_status="EXACT", identity_reason="exact_model"),
        SimpleNamespace(url="https://bad.example/manual.pdf", title="Other Product Manual", snippet="", score=.5, likely_official=False, provenance=None, identity_score=0, identity_status="UNVERIFIED", identity_reason=""),
    ]
    monkeypatch.setattr(service, "discover_pdf_documents", lambda *_args, **_kwargs: (resolved, rows))

    good = tmp_path / "good.pdf"
    good.write_bytes(b"%PDF-fake")
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-bad")

    def fake_inspect(_identity, url, _cache_dir, **kwargs):
        from product_intelligence.pdf_review import PdfInspection
        if "bad.example" in url:
            return PdfInspection(url, url, bad, False, False, False, 0.0, "identity_conflict", 2, 100, False, b"", 0, False, kwargs.get("provenance"))
        return PdfInspection(url, "https://cdn.acme.example/final.pdf", good, True, False, False, .98, "exact_model", 2, 500, False, b"", 95, True, kwargs.get("provenance"))

    monkeypatch.setattr(service, "inspect_pdf_candidate", fake_inspect)
    monkeypatch.setattr(service, "sha256_file", lambda _path: "samehash")

    result = service.discover_validated_review_pdfs(identity, tmp_path, limit=8)
    assert len(result.candidates) == 1
    assert result.candidates[0].inspection.identity_accepted is True
    assert result.rejected_count == 1
    assert result.duplicate_count == 1


def test_review_service_has_no_ocr_or_mistral_runtime_dependency():
    source = Path("src/product_intelligence/pdf_pipeline.py").read_text(encoding="utf-8").lower()
    for forbidden in ("ocr_space_client", "remote_ocr_text", "mistral_client", "remote_mistral", "mistralai"):
        assert forbidden not in source


def test_review_plan_zero_selection_is_enforced_and_does_not_fall_back(monkeypatch, tmp_path):
    from product_intelligence import pdf_review_batch
    from product_intelligence.batch import BatchItem

    calls = {"base": 0}
    item = BatchItem(
        row=2,
        sheet="Sheet1",
        identity=ProductIdentity(mpn="ABC123", model="ABC123"),
        source_urls=[],
        source_url=None,
    )

    def base_scrape(*_args, **_kwargs):
        calls["base"] += 1
        return "ok"

    monkeypatch.setattr(pdf_review_batch, "_BASE_SCRAPE_ITEM", base_scrape)
    monkeypatch.setattr(pdf_review_batch.batch_module, "_ingest_direct_documents", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("automatic discovery restarted")))

    result = pdf_review_batch.scrape_item_with_review(
        item,
        str(tmp_path),
        approved_urls=[],
        enforced=True,
    )
    assert result == "ok"
    assert calls["base"] == 1


def test_real_review_shell_search_uses_part_number_pdf_service():
    source = Path("src/product_intelligence/real_pdf_review_shell.py").read_text(encoding="utf-8")
    assert "search_product_pdfs_by_part_number" in source
    assert "discover_review_candidates" not in source


def test_automatic_and_review_batch_share_identity_first_pdf_engine():
    source = Path("src/product_intelligence/pdf_review_batch.py").read_text(encoding="utf-8")
    assert "discover_pdf_documents" in source
    assert "resolve_pdf_identity" in source
    assert "batch_module.discover_product_documents = _shared_discover" in source
    assert "batch_module.process_pdf_document = _shared_process_pdf" in source


def test_packaged_launcher_does_not_depend_on_runtime_hardening_patch():
    source = Path("run_desktop.py").read_text(encoding="utf-8")
    assert "real_pdf_review_shell" in source
    assert "install_excel_pdf_review_hardening" not in source
