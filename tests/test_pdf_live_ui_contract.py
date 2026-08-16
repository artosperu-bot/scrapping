from types import SimpleNamespace

from product_intelligence import part_number_pdf_search as search_module
from product_intelligence.live_ui_desktop import App


def _candidate(url="https://docs.test/manual.pdf", pages=4):
    candidate = SimpleNamespace(
        url=url,
        title="Manual",
        snippet="",
        document_type="manual",
        likely_official=True,
        discovery_score=9.0,
        provenance="official",
        identity_status="VALIDATED",
        identity_reason="exact",
        identity_score=10,
        review_score=10.0,
    )
    inspection = SimpleNamespace(
        page_count=pages,
        final_url=url,
        identity_accepted=True,
        identity_provenance_bound=False,
        identity_reason="exact",
        review_score=10.0,
        local_path="unused.pdf",
    )
    return SimpleNamespace(candidate=candidate, inspection=inspection, sha256="abc")


def _result(rows):
    identity = SimpleNamespace(brand="JBL", model="Quantum 350", product_name="Quantum 350")
    return SimpleNamespace(
        resolved=SimpleNamespace(identity=identity),
        candidates=tuple(rows),
        discovered_count=len(rows),
        downloaded_count=len(rows),
        validated_count=len(rows),
        rejected_count=0,
        duplicate_count=0,
    )


def test_search_product_pdfs_emits_validated_candidate_before_done(monkeypatch, tmp_path):
    row = _candidate()

    def fake_discover(*_args, on_event=None, **_kwargs):
        assert on_event is not None
        on_event({"type": "validated", "row": row})
        return _result([row])

    monkeypatch.setattr(search_module, "discover_validated_review_pdfs", fake_discover)
    events = []
    result = search_module.search_product_pdfs(
        tmp_path,
        mpn="JBLQ350WLBLKAM",
        brand="JBL",
        model="Quantum 350",
        on_event=events.append,
    )

    assert result.validated_count == 1
    kinds = [event["type"] for event in events]
    assert "validated" in kinds
    assert kinds[-1] == "done"
    assert kinds.index("validated") < kinds.index("done")


def test_page_limit_candidate_is_rejected_before_it_can_be_rendered(monkeypatch, tmp_path):
    row = _candidate(pages=14)

    def fake_discover(*_args, on_event=None, **_kwargs):
        on_event({"type": "validated", "row": row})
        return _result([row])

    monkeypatch.setattr(search_module, "discover_validated_review_pdfs", fake_discover)
    events = []
    result = search_module.search_product_pdfs(tmp_path, mpn="ABC-1", on_event=events.append)

    assert result.validated_count == 0
    assert not any(event["type"] == "validated" for event in events)
    assert any(event["type"] == "rejected" and event.get("reason") == "PAGE_LIMIT" for event in events)


def test_pdf_validated_event_populates_review_collection_incrementally():
    row = _candidate()
    app = App.__new__(App)
    app._pdf_review_candidates = {0: []}
    app._pdf_review_inspections = {0: {}}
    app._pdf_review_selected = {0: set()}
    app._pdf_review_enforced = {0}
    app._pdf_live_counts = {}
    app._pdf_review_refresh_tree = lambda: None
    app._pdf_review_product_index = lambda: 0
    app._apply_pdf_live_event(0, {"type": "validated", "row": row})

    assert [item.url for item in app._pdf_review_candidates[0]] == [row.candidate.url]
    assert app._pdf_review_inspections[0][row.candidate.url] is row.inspection
    assert 0 not in app._pdf_review_enforced
