from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from product_intelligence import live_pdf_discovery as live
from product_intelligence import pdf_desktop_e2e as desktop_e2e
from product_intelligence import pdf_review
from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_desktop_e2e import PdfDesktopE2EMixin
from product_intelligence.pdf_pipeline import ResolvedPdfIdentity
from product_intelligence.pdf_review import PdfReviewCandidate


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _EventBase:
    def _apply_pdf_live_event(self, _index: int, event: dict):
        return event


class _Harness(PdfDesktopE2EMixin, _EventBase):
    def _pdf_review_product_index(self):
        return 0

    def _identity_for_index(self, _index: int):
        return ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")


def test_p60_search_trace_forwards_each_query_as_live_numbered_event(monkeypatch, tmp_path):
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    resolved = ResolvedPdfIdentity(identity, identity, "jbl.com", "RESOLVED", 0.99, {})

    monkeypatch.setattr(live, "resolve_pdf_identity", lambda *_args, **_kwargs: resolved)

    def fake_discovery(_identity, *, trace=None, **_kwargs):
        assert trace is not None
        trace.emit("PDF_SEARCH_QUERY", query='site:jbl.com "Quantum 350 Wireless" manual')
        return []

    monkeypatch.setattr(live, "discover_review_product_documents", fake_discovery)

    events = []
    result = live.discover_validated_review_pdfs_live(
        identity,
        tmp_path,
        limit=8,
        timeout=1,
        on_event=events.append,
    )

    assert result.validated_count == 0
    queries = [event for event in events if event.get("type") == "query"]
    assert queries == [
        {
            "type": "query",
            "stage": "SEARCH",
            "status": "SEARCHING",
            "position": 1,
            "limit": 8,
            "query": 'site:jbl.com "Quantum 350 Wireless" manual',
        }
    ]


def test_pdf_inspection_exposes_post_download_stage_callback():
    assert "on_stage" in inspect.signature(pdf_review.inspect_pdf_candidate).parameters


def test_live_discovery_emits_downloaded_then_validating_before_acceptance(monkeypatch, tmp_path):
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    resolved = ResolvedPdfIdentity(identity, identity, "jbl.com", "RESOLVED", 0.99, {})
    candidate = PdfReviewCandidate(
        url="https://support.jbl.com/quantum350/Owners_Manual.pdf",
        title="Quantum 350 Owner's Manual",
        document_type="manual",
        likely_official=True,
    )
    local_pdf = tmp_path / "Owners_Manual.pdf"

    monkeypatch.setattr(live, "resolve_pdf_identity", lambda *_args, **_kwargs: resolved)
    monkeypatch.setattr(live, "discover_review_product_documents", lambda *_args, **_kwargs: [object()])
    monkeypatch.setattr(live, "_review_candidate", lambda _row: candidate)

    def fake_inspection(_identity, _url, _cache, *, on_stage, **_kwargs):
        local_pdf.write_bytes(b"%PDF-1.4\n% runtime validating fixture\n")
        on_stage("downloaded", local_path=local_pdf, final_url=candidate.url)
        on_stage("validating", local_path=local_pdf, final_url=candidate.url)
        return SimpleNamespace(
            local_path=local_pdf,
            final_url=candidate.url,
            identity_accepted=True,
            identity_provenance_bound=False,
            identity_reason="exact_model",
            page_count=7,
            review_score=95,
        )

    monkeypatch.setattr(live, "inspect_pdf_candidate", fake_inspection)

    events: list[dict] = []
    result = live.discover_validated_review_pdfs_live(
        identity,
        tmp_path,
        limit=8,
        timeout=1,
        on_event=events.append,
    )

    assert result.validated_count == 1
    stages = [
        (event.get("type"), event.get("status"))
        for event in events
        if event.get("type") in {"download", "validation", "validated"}
    ]
    assert stages == [
        ("download", "STARTED"),
        ("download", "FINISHED"),
        ("validation", "STARTED"),
        ("validated", None),
    ]
    validation = next(event for event in events if event.get("type") == "validation")
    assert validation["local_path"] == str(local_pdf)


def test_desktop_pdf_events_expose_concrete_runtime_detail_and_physical_path(tmp_path):
    app = _Harness()
    logs: list[str] = []
    stages: list[str] = []
    app.emit = logs.append
    app._excel_progress_stage = stages.append
    app.out = _Value(str(tmp_path))

    local_pdf = tmp_path / "pdf_review" / "JBLQ350WLBLKAM" / "Owners_Manual.pdf"
    local_pdf.parent.mkdir(parents=True)
    local_pdf.write_bytes(b"%PDF-1.4\n% runtime contract fixture\n")

    row = SimpleNamespace(
        candidate=SimpleNamespace(
            url="https://support.jbl.com/quantum350/Owners_Manual.pdf",
            title="Quantum 350 Owner's Manual",
        ),
        inspection=SimpleNamespace(
            local_path=str(local_pdf),
            page_count=7,
            final_url="https://support.jbl.com/quantum350/Owners_Manual.pdf",
        ),
    )

    app._apply_pdf_live_event(
        0,
        {
            "type": "query",
            "stage": "SEARCH",
            "status": "SEARCHING",
            "position": 3,
            "limit": 8,
            "query": 'site:jbl.com "Quantum 350 Wireless" manual',
        },
    )
    app._apply_pdf_live_event(
        0,
        {
            "type": "identity",
            "stage": "SEARCH",
            "brand": "JBL",
            "model": "Quantum 350 Wireless",
            "official_domain": "jbl.com",
            "status": "RESOLVED",
        },
    )
    app._apply_pdf_live_event(
        0,
        {
            "type": "candidate",
            "stage": "VALIDATE",
            "url": row.candidate.url,
            "title": row.candidate.title,
            "position": 1,
            "total": 2,
        },
    )
    app._apply_pdf_live_event(
        0,
        {"type": "download", "stage": "DOWNLOAD", "status": "STARTED", "url": row.candidate.url},
    )
    app._apply_pdf_live_event(
        0,
        {
            "type": "download",
            "stage": "DOWNLOAD",
            "status": "FINISHED",
            "url": row.candidate.url,
            "local_path": str(local_pdf),
        },
    )
    app._apply_pdf_live_event(
        0,
        {
            "type": "validation",
            "stage": "VALIDATE",
            "status": "STARTED",
            "url": row.candidate.url,
            "local_path": str(local_pdf),
        },
    )
    app._apply_pdf_live_event(
        0,
        {"type": "validated", "stage": "VALIDATE", "row": row, "url": row.candidate.url, "pages": 7},
    )
    app._apply_pdf_live_event(
        0,
        {
            "type": "rejected",
            "stage": "VALIDATE",
            "url": "https://cdn.example/wrong.pdf",
            "reason": "IDENTITY_MISMATCH",
            "pages": 5,
        },
    )
    app._apply_pdf_live_event(
        0,
        {
            "type": "final_result",
            "result": SimpleNamespace(
                discovered_count=2,
                downloaded_count=2,
                validated_count=1,
                rejected_count=1,
            ),
        },
    )

    joined = "\n".join(logs)
    assert "QUERY 3/8" in joined
    assert 'site:jbl.com "Quantum 350 Wireless" manual' in joined
    assert "IDENTIDAD" in joined and "JBL" in joined and "Quantum 350 Wireless" in joined and "jbl.com" in joined
    assert "ENCONTRADO" in joined and row.candidate.url in joined and row.candidate.title in joined
    assert "DESCARGANDO" in joined and row.candidate.url in joined
    assert "DESCARGADO" in joined and str(local_pdf) in joined
    assert "VALIDANDO" in joined and str(local_pdf) in joined
    assert "ACEPTADO" in joined and "Owners_Manual.pdf" in joined and "pages=7" in joined
    assert "RECHAZADO" in joined and "IDENTITY_MISMATCH" in joined and "wrong.pdf" in joined
    assert "FIN" in joined and "descubiertos=2" in joined and "validados=1" in joined and "rechazados=1" in joined
    assert local_pdf.is_file()
    assert any("3/8" in stage for stage in stages)
    assert any("validando" in stage.lower() for stage in stages)


def test_execute_pdf_runtime_state_tracks_real_counts_and_monotonic_progress():
    state_cls = getattr(desktop_e2e, "PdfExecuteRuntimeState", None)
    assert state_cls is not None, "Execute needs a dedicated PDF runtime state, not only generic log text"

    state = state_cls()
    progress = []
    events = [
        {"type": "query", "position": 1, "limit": 8, "query": "q1"},
        {"type": "query", "position": 3, "limit": 8, "query": "q3"},
        {"type": "candidate", "position": 1, "total": 2, "url": "https://example/a.pdf"},
        {"type": "download", "status": "STARTED", "url": "https://example/a.pdf"},
        {"type": "download", "status": "FINISHED", "url": "https://example/a.pdf", "local_path": "C:/pdf/a.pdf"},
        {"type": "validation", "status": "STARTED", "url": "https://example/a.pdf", "local_path": "C:/pdf/a.pdf"},
        {"type": "validated", "url": "https://example/a.pdf"},
        {"type": "rejected", "url": "https://example/b.pdf", "reason": "IDENTITY_MISMATCH"},
    ]
    for event in events:
        state.apply(event)
        progress.append(state.progress)

    assert state.query_position == 3
    assert state.query_limit == 8
    assert state.found == 1
    assert state.downloaded == 1
    assert state.validated == 1
    assert state.rejected == 1
    assert progress == sorted(progress)

    state.apply(
        {
            "type": "final_result",
            "result": SimpleNamespace(
                discovered_count=7,
                downloaded_count=4,
                validated_count=4,
                rejected_count=3,
            ),
        }
    )
    assert state.progress == 100
    assert state.found == 7
    assert state.downloaded == 4
    assert state.validated == 4
    assert state.rejected == 3


def test_execute_workspace_mixin_owns_real_pdf_panel_installation():
    assert "_install_excel_progress" in PdfDesktopE2EMixin.__dict__, "PDF panel must be installed in Ejecutar"
    assert "_update_pdf_execute_panel" in PdfDesktopE2EMixin.__dict__, "Live PDF events must update the Ejecutar panel"
