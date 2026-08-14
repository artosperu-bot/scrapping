from pathlib import Path

import pytest

from product_intelligence.discovery import SearchCandidate
from product_intelligence.document_discovery import resolve_document_candidate_urls
from product_intelligence.models import ProductIdentity
from product_intelligence.progress_animation import ProgressAnimation
from product_intelligence.provider_settings import ProviderSettings


def test_repeated_running_same_gif_does_not_restart_active_animation(monkeypatch):
    animation = object.__new__(ProgressAnimation)
    animation._asset_name = "processing.gif"
    animation._frames = [(object(), 80), (object(), 80)]
    animation._frame_index = 1
    animation._after_id = "already-scheduled"

    cancelled = []
    shown = []
    monkeypatch.setattr(animation, "_cancel_tick", lambda: cancelled.append(True))
    monkeypatch.setattr(animation, "_show_frame", lambda: shown.append(True))

    animation._use_asset("processing.gif", animate=True)

    assert cancelled == []
    assert shown == []
    assert animation._frame_index == 1
    assert animation._after_id == "already-scheduled"


def test_provider_settings_save_is_read_back_verifiable(tmp_path):
    path = tmp_path / "settings.json"
    settings = ProviderSettings(path)
    settings.set("request_timeout", 21)
    settings.set("ocr_space_enabled", True)
    settings.set("mistral_enabled", True)
    settings.save()

    persisted = ProviderSettings(path)
    assert persisted.as_dict() == settings.as_dict()
    assert persisted.get("request_timeout") == 21


def test_provider_desktop_exposes_inline_save_status():
    source = Path("src/product_intelligence/provider_desktop.py").read_text(encoding="utf-8")
    assert "settings_save_status" in source
    assert "GUARDADO" in source
    assert "ERROR AL GUARDAR" in source


def test_html_document_landing_page_resolves_pdf_links(monkeypatch):
    identity = ProductIdentity(brand="JBL", model="Tune 530C", mpn="JBLT530CBLKAM")
    landing = SearchCandidate(
        "https://www.jbl.com/JBLT530CBLKAM.html",
        "JBL Tune 530C",
        "Specs & Downloads Spec Sheet",
        .95,
        True,
    )

    class Response:
        text = '<html><a href="/docs/JBLT530C_SpecSheet.pdf">Spec Sheet</a></html>'
        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "product_intelligence.document_discovery.requests.get",
        lambda *args, **kwargs: Response(),
    )

    resolved = resolve_document_candidate_urls(identity, landing, timeout=1)
    assert [row.url for row in resolved] == ["https://www.jbl.com/docs/JBLT530C_SpecSheet.pdf"]
    assert resolved[0].likely_official is True


def test_direct_pdf_candidate_is_not_refetched(monkeypatch):
    identity = ProductIdentity(mpn="JBLQ350WLBLKAM")
    direct = SearchCandidate(
        "https://support.jbl.com/JBLQ350WLBLKAM/manual.pdf",
        "User Manual",
        "JBLQ350WLBLKAM",
        .9,
        True,
    )
    monkeypatch.setattr(
        "product_intelligence.document_discovery.requests.get",
        lambda *args, **kwargs: pytest.fail("direct PDF should not fetch landing HTML"),
    )
    assert resolve_document_candidate_urls(identity, direct, timeout=1) == [direct]
