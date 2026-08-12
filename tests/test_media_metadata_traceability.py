from types import SimpleNamespace

from product_intelligence.models import ProductIdentity
import product_intelligence.media_workflow as workflow


def test_official_page_results_are_tagged_with_origin_and_small_rejections_are_not_returned(monkeypatch, tmp_path):
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    monkeypatch.setattr(workflow, "search_web", lambda *_a, **_k: [])
    monkeypatch.setattr(workflow, "fetch_page", lambda u, **_k: SimpleNamespace(
        final_url="https://www.jbl.com.pe/QUANTUM350WIRELESS-.html",
        html="JBL Quantum 350 Wireless JBLQ350WLBLKAM",
        network_resources=[], status_code=200, method="playwright"))
    monkeypatch.setattr(workflow, "discover_media", lambda *_a, **_k: [
        {"url":"https://cdn.jbl.com/large.jpg","media_type":"image","scope":"EXACT_PRODUCT","confidence":0.90,"role":"product_gallery","autofill_eligible":False},
        {"url":"https://youtube.com/embed/demo","media_type":"video","provider":"youtube","scope":"EXACT_PRODUCT","confidence":0.90,"role":"product_video","autofill_eligible":False},
    ])

    def fake_download(item, *_a, **_k):
        if item["media_type"] == "image":
            return {**item, "downloaded": False, "metadata_only": False, "reason": "image_too_small", "width": 120, "height": 120, "pixel_area": 14400}
        return {**item, "downloaded": False, "metadata_only": True, "reason": "hosted_video"}

    monkeypatch.setattr(workflow, "download_media_item", fake_download)
    captured = {}
    monkeypatch.setattr(workflow, "write_media_metadata", lambda _root, _ident, rows: captured.setdefault("rows", list(rows)))

    events = []
    rows = workflow.run_media_product(
        identity, tmp_path,
        manual_urls=["https://www.jbl.com.pe/QUANTUM350WIRELESS-.html"],
        auto_search=False,
        on_event=events.append,
    )
    assert len(rows) == 1
    assert rows[0]["media_type"] == "video"
    assert rows[0]["metadata_only"] is True
    assert rows[0]["official_page"] is True
    assert rows[0]["page_discovery_source"] == "manual"
    assert captured["rows"] == rows
    assert any(e.get("type") == "media_rejected" and e.get("reason") == "image_too_small" for e in events)
