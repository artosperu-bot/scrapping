from types import SimpleNamespace

from product_intelligence import document_discovery
from product_intelligence.excel_pdf_review_hardening import (
    prepare_document_identity,
    review_gate_missing_indices,
)
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

    effective, domain = prepare_document_identity(source, timeout=8)
    assert effective.brand == "Acme"
    assert effective.model == "Model X"
    assert effective.mpn == "ABC123"
    assert domain == "acme.example"

    queries = document_discovery.build_document_queries(effective, official_domain=domain)
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
    # Confirming zero PDFs is still a valid review decision; enforcement is what matters.
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


def test_review_hardening_preserves_web_as_independent_source():
    shell_source = open("src/product_intelligence/pdf_review_shell.py", encoding="utf-8").read()
    hardening_source = open("src/product_intelligence/excel_pdf_review_hardening.py", encoding="utf-8").read()
    assert "self.source_web_enabled.set(False)" not in shell_source
    assert "self.source_web_enabled.set(False)" not in hardening_source


def test_packaged_launcher_installs_hardening_before_final_main():
    source = open("run_desktop.py", encoding="utf-8").read()
    assert "install_excel_pdf_review_hardening()" in source
    assert source.index("install_excel_pdf_review_hardening()") < source.rindex("managed_main()")
