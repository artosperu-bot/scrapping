from types import SimpleNamespace

from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_evidence import discover_pdf_candidates
from product_intelligence.pdf_review_search_strategy import build_review_query_tiers


def _flatten(tiers):
    return [query for tier in tiers for query in tier]


def test_resolved_identity_prioritizes_canonical_document_queries_before_identifier_expansion():
    identity = ProductIdentity(
        brand="Acme",
        manufacturer="Acme Corporation",
        model="Endurance Run 3 Wireless",
        mpn="ABC123XYZ",
    )
    queries = _flatten(build_review_query_tiers(identity, official_domain="acme.com"))
    canonical_positions = [i for i, q in enumerate(queries) if "endurance run 3 wireless" in q.lower()]
    identifier_expansion_positions = [
        i for i, q in enumerate(queries)
        if "abc123xyz" in q.lower()
        and any(term in q.lower() for term in ("manual", "datasheet", "specifications", "support"))
    ]
    assert canonical_positions, queries
    assert identifier_expansion_positions, queries
    assert min(canonical_positions) < min(identifier_expansion_positions), queries
    assert min(canonical_positions) < 4, queries


def test_social_tracking_pdf_endpoint_is_rejected_before_candidate_extraction():
    html = '''
    <a href="https://connect.facebook.net/en_US/.pdf">Acme Tune 530C manual</a>
    <a href="/docs/acme-tune-530c-manual.pdf">Download manual</a>
    '''
    urls = [row.url for row in discover_pdf_candidates(html, "https://retailer.example/product/abc123")]
    assert "https://connect.facebook.net/en_US/.pdf" not in urls
    assert "https://retailer.example/docs/acme-tune-530c-manual.pdf" in urls


def test_malformed_backslash_pdf_endpoint_is_rejected_before_candidate_extraction():
    html = '''
    <a href="/%5C.pdf">Acme Endurance Run 3 manual</a>
    <a href="/docs/endurance-run-3-manual.pdf">Download manual</a>
    '''
    urls = [row.url for row in discover_pdf_candidates(html, "https://retailer.example/product/abc123")]
    assert "https://retailer.example/%5C.pdf" not in urls
    assert "https://retailer.example/docs/endurance-run-3-manual.pdf" in urls


def test_raw_resolved_pdf_links_do_not_stop_review_discovery_before_later_strategy(monkeypatch):
    """A raw child PDF is discovery evidence, not a validated-document stop condition."""
    from product_intelligence import pdf_review_search_strategy as strategy

    identity = ProductIdentity(brand="Acme", model="Model X", mpn="ABC123")
    attempted: list[str] = []

    fake_parent = SimpleNamespace(
        url="https://acme.example/model-x",
        title="Acme Model X ABC123",
        snippet="",
        score=1.0,
        likely_official=True,
        identity_score=100,
    )
    later_direct = SimpleNamespace(
        url="https://acme.example/docs/model-x-specification-sheet.pdf",
        title="Acme Model X Specification Sheet ABC123",
        snippet="",
        score=1.0,
        likely_official=True,
        identity_score=100,
    )
    fake_child = SimpleNamespace(
        url="https://acme.example/static/generated.pdf",
        title="generated",
        snippet="",
        score=.5,
        likely_official=True,
        identity_score=85,
    )

    monkeypatch.setattr(strategy, "build_review_query_tiers", lambda *_a, **_k: [["first-strategy", "later-strategy"]])
    monkeypatch.setattr(strategy, "_discover_official_pdp_documents", lambda *_a, **_k: [])

    def search(_identity, query, **_kwargs):
        attempted.append(query)
        return [fake_parent] if query == "first-strategy" else [later_direct]

    monkeypatch.setattr(strategy.core, "search_web_query_candidates", search)
    monkeypatch.setattr(strategy.core, "_accept_search_candidate", lambda _i, row, trace=None: row)

    def resolve(_identity, rows, **_kwargs):
        if any(row.url == fake_parent.url for row in rows):
            return [fake_child]
        return list(rows)

    monkeypatch.setattr(strategy.core, "_resolve_valid_candidates", resolve)

    rows = strategy.discover_review_product_documents(identity, limit=4, timeout=1)
    urls = [row.url for row in rows]

    assert attempted == ["first-strategy", "later-strategy"]
    assert later_direct.url in urls


def test_live_pdf_search_never_exceeds_eight_queries_across_authority_retry(monkeypatch, tmp_path):
    """MAX_QUERY_ATTEMPTS is a per-product end-to-end budget, not a per-pass budget."""
    from product_intelligence import live_pdf_discovery as live
    from product_intelligence import pdf_review_search_strategy as strategy
    from product_intelligence.pdf_pipeline import ResolvedPdfIdentity

    identity = ProductIdentity(brand="Acme", model="Model X", mpn="ABC123")
    resolved = ResolvedPdfIdentity(identity, identity, None, "RESOLVED", .95, {})
    attempted: list[str] = []

    monkeypatch.setattr(live, "resolve_pdf_identity", lambda *_a, **_k: resolved)
    monkeypatch.setattr(live, "_brand_aligned_domain", lambda *_a, **_k: "acme.com")

    def search(_identity, query, **_kwargs):
        attempted.append(query)
        return []

    monkeypatch.setattr(strategy.core, "search_web_query_candidates", search)
    monkeypatch.setattr(strategy.core, "_browser_document_pass", lambda *_a, **_k: [])
    monkeypatch.setattr(strategy.core, "search_web", lambda *_a, **_k: [])

    result = live.discover_validated_review_pdfs_live(identity, tmp_path, limit=8, timeout=1)

    assert result.validated_count == 0
    assert len(attempted) <= strategy.core.MAX_QUERY_ATTEMPTS, attempted


def test_packaged_desktop_batch_retains_processed_pdf_under_output_pdf_evidence(monkeypatch, tmp_path):
    """A P60 PDF used by the real desktop must survive after processing."""
    from product_intelligence import pdf_review_batch as review_batch

    identity = ProductIdentity(brand="Acme", model="Model X", mpn="ABC123")
    item = SimpleNamespace(identity=identity)
    captured = {}

    monkeypatch.setattr(
        review_batch,
        "resolve_pdf_identity",
        lambda *_a, **_k: SimpleNamespace(identity=identity),
    )

    def fake_process(_identity, url, *args, **kwargs):
        captured["url"] = url
        captured["download_dir"] = kwargs.get("download_dir")
        return SimpleNamespace()

    def fake_scrape(_item, _out_dir, **_kwargs):
        return review_batch.batch_module.process_pdf_document(identity, "https://acme.example/manual.pdf")

    def fake_run(*_args, **_kwargs):
        return review_batch.batch_module.scrape_item(item, str(tmp_path / "json"))

    monkeypatch.setattr(review_batch, "_BASE_PROCESS_PDF", fake_process)
    monkeypatch.setattr(review_batch, "_BASE_SCRAPE_ITEM", fake_scrape)
    monkeypatch.setattr(review_batch, "_BASE_RUN_BATCH", fake_run)

    review_batch.run_batch_with_review()

    expected = tmp_path / "pdf_evidence" / "ABC123"
    assert captured["url"].endswith("manual.pdf")
    assert captured["download_dir"] == expected
    assert expected.is_dir()
