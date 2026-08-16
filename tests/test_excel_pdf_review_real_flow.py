from types import SimpleNamespace

from product_intelligence import document_discovery
from product_intelligence.pdf_pipeline import resolve_pdf_identity
from product_intelligence.real_pdf_review_shell import review_gate_missing_indices
from product_intelligence.models import ProductIdentity


def test_mpn_only_identity_is_bootstrapped_before_pdf_queries(monkeypatch):
    source = ProductIdentity(mpn="ABC123", model="ABC123")
    enriched = ProductIdentity(mpn="ABC123", brand="Acme", model="Model X")

    from product_intelligence import identity_bootstrap

    monkeypatch.setattr(
        identity_bootstrap,
        "bootstrap_identity",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="RESOLVED",
            identity=enriched,
            official_domain_hint="acme.example",
        ),
    )

    resolved = resolve_pdf_identity(source, timeout=8)
    assert resolved.identity.brand == "Acme"
    assert resolved.identity.model == "Model X"
    assert resolved.identity.mpn == "ABC123"
    assert resolved.official_domain == "acme.example"

    queries = document_discovery.build_document_queries(resolved.identity, official_domain=resolved.official_domain)
    assert any('"Acme" "ABC123"' in query for query in queries)
    assert any("site:acme.example" in query for query in queries)
    assert not any('"ABC123" "ABC123"' in query for query in queries)


def test_reviewed_pdf_mode_blocks_excel_until_every_product_is_confirmed():
    assert review_gate_missing_indices(
        total_products=3,
        reviewed_mode=True,
        pdf_enabled=True,
        enforced_indices={0},
    ) == [1, 2]
    assert review_gate_missing_indices(
        total_products=3,
        reviewed_mode=True,
        pdf_enabled=True,
        enforced_indices={0, 1, 2},
    ) == []
    assert review_gate_missing_indices(
        total_products=3,
        reviewed_mode=False,
        pdf_enabled=True,
        enforced_indices=set(),
    ) == []
    assert review_gate_missing_indices(
        total_products=3,
        reviewed_mode=True,
        pdf_enabled=False,
        enforced_indices=set(),
    ) == []


def test_real_review_preserves_web_as_independent_source():
    source = open("src/product_intelligence/real_pdf_review_shell.py", encoding="utf-8").read()
    assert "self.source_web_enabled.set(False)" not in source


def test_packaged_launcher_routes_directly_to_real_pipeline():
    source = open("run_desktop.py", encoding="utf-8").read()
    assert "real_pdf_review_shell" in source
    assert "install_excel_pdf_review_hardening" not in source
    assert "managed_main = pdf_review_main" in source
    assert source.rstrip().endswith("managed_main()")
