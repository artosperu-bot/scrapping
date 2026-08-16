from types import SimpleNamespace

from product_intelligence.models import ProductIdentity


def test_web_resolved_identity_does_not_call_upc_provider(monkeypatch):
    from product_intelligence import pdf_pipeline

    source = ProductIdentity(mpn="PN123", ean="0123456789012", model="PN123")
    resolved = ProductIdentity(mpn="PN123", ean="0123456789012", brand="Acme", model="Nova X100", product_name="Acme Nova X100")

    monkeypatch.setattr(
        "product_intelligence.identity_bootstrap.bootstrap_identity",
        lambda *_a, **_k: SimpleNamespace(status="RESOLVED", identity=resolved, official_domain_hint="acme.example", confidence=.95, page_signals=[]),
    )
    calls = {"upc": 0}
    monkeypatch.setattr(pdf_pipeline, "lookup_identity_by_trade_code", lambda *_a, **_k: calls.__setitem__("upc", calls["upc"] + 1))

    result = pdf_pipeline.resolve_pdf_identity(source)
    assert result.status == "RESOLVED"
    assert calls["upc"] == 0


def test_partial_mpn_identity_uses_ean_lookup_once(monkeypatch):
    from product_intelligence import pdf_pipeline
    from product_intelligence.upcitemdb_provider import UpcLookupResult

    source = ProductIdentity(mpn="PN123", ean="0123456789012", model="PN123")
    partial = ProductIdentity(mpn="PN123", ean="0123456789012", model="PN123")
    monkeypatch.setattr(
        "product_intelligence.identity_bootstrap.bootstrap_identity",
        lambda *_a, **_k: SimpleNamespace(status="UNRESOLVED", identity=partial, official_domain_hint=None, confidence=.1, page_signals=[]),
    )
    monkeypatch.setattr(pdf_pipeline, "refine_code_identity", lambda original, current, **_k: SimpleNamespace(identity=current, official_domain_hint=None, candidates_used=0, brand_support_domains=0, model_support_domains=0))
    calls = []
    monkeypatch.setattr(
        pdf_pipeline,
        "lookup_identity_by_trade_code",
        lambda code, **_k: calls.append(code) or UpcLookupResult(
            status="OK",
            identifier=code,
            identity=ProductIdentity(ean=code, brand="Acme", manufacturer="Acme", model="Nova X100", product_name="Acme Nova X100"),
            source="HTTP",
            rate_limit_remaining=77,
        ),
    )

    result = pdf_pipeline.resolve_pdf_identity(source)
    assert calls == ["0123456789012"]
    assert result.identity.brand == "Acme"
    assert result.identity.model == "Nova X100"
    assert result.identity.mpn == "PN123"
    assert "UPCITEMDB" in result.diagnostics["providers_used"]


def test_upc_not_found_does_not_crash_or_replace_identity(monkeypatch):
    from product_intelligence import pdf_pipeline
    from product_intelligence.upcitemdb_provider import UpcLookupResult

    source = ProductIdentity(upc="123456789012", model="123456789012")
    monkeypatch.setattr("product_intelligence.identity_bootstrap.bootstrap_identity", lambda *_a, **_k: SimpleNamespace(status="UNRESOLVED", identity=source, official_domain_hint=None, confidence=0, page_signals=[]))
    monkeypatch.setattr(pdf_pipeline, "refine_code_identity", lambda original, current, **_k: SimpleNamespace(identity=current, official_domain_hint=None, candidates_used=0, brand_support_domains=0, model_support_domains=0))
    monkeypatch.setattr(pdf_pipeline, "lookup_identity_by_trade_code", lambda code, **_k: UpcLookupResult(status="NOT_FOUND", identifier=code, identity=None, source="HTTP"))

    result = pdf_pipeline.resolve_pdf_identity(source)
    assert result.status == "PARTIAL_IDENTITY"
    assert result.identity.upc == "123456789012"


def test_conflicting_trade_code_is_fail_closed(monkeypatch):
    from product_intelligence import pdf_pipeline
    from product_intelligence.upcitemdb_provider import UpcLookupResult

    source = ProductIdentity(ean="1111111111111", model="1111111111111")
    monkeypatch.setattr("product_intelligence.identity_bootstrap.bootstrap_identity", lambda *_a, **_k: SimpleNamespace(status="UNRESOLVED", identity=source, official_domain_hint=None, confidence=0, page_signals=[]))
    monkeypatch.setattr(pdf_pipeline, "refine_code_identity", lambda original, current, **_k: SimpleNamespace(identity=current, official_domain_hint=None, candidates_used=0, brand_support_domains=0, model_support_domains=0))
    monkeypatch.setattr(
        pdf_pipeline,
        "lookup_identity_by_trade_code",
        lambda code, **_k: UpcLookupResult(status="OK", identifier=code, identity=ProductIdentity(ean="2222222222222", brand="Wrong", model="Wrong X"), source="HTTP"),
    )

    result = pdf_pipeline.resolve_pdf_identity(source)
    assert result.status == "CONFLICT"
    assert result.identity.ean == "1111111111111"


def test_provider_cache_reuses_success_and_negative_results(monkeypatch, tmp_path):
    from product_intelligence.upcitemdb_provider import UpcItemDbIdentityProvider

    provider = UpcItemDbIdentityProvider(cache_path=tmp_path / "identity-cache.json")
    calls = {"http": 0}

    class Response:
        status_code = 200
        headers = {"X-RateLimit-Remaining": "88"}
        def json(self):
            return {"code": "OK", "items": [{"ean": "0123456789012", "brand": "Acme", "model": "Nova X100", "title": "Acme Nova X100"}]}

    def fake_get(*_a, **_k):
        calls["http"] += 1
        return Response()

    monkeypatch.setattr(provider.session, "get", fake_get)
    first = provider.lookup("0123456789012")
    second = provider.lookup("0123456789012")
    assert first.status == "OK"
    assert second.source == "CACHE"
    assert calls["http"] == 1
