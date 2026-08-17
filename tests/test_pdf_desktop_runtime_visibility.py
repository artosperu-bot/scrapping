from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from product_intelligence import live_pdf_discovery as live
from product_intelligence.models import ProductIdentity
from product_intelligence.pdf_desktop_e2e import PdfDesktopE2EMixin
from product_intelligence.pdf_pipeline import ResolvedPdfIdentity


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
            "stage": "VALIDATE",
            "status": "FINISHED",
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
    assert "ACEPTADO" in joined and "Owners_Manual.pdf" in joined and "pages=7" in joined
    assert "RECHAZADO" in joined and "IDENTITY_MISMATCH" in joined and "wrong.pdf" in joined
    assert "FIN" in joined and "descubiertos=2" in joined and "validados=1" in joined and "rechazados=1" in joined
    assert local_pdf.is_file()
    assert any("3/8" in stage for stage in stages)
