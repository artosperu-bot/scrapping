from types import SimpleNamespace
from product_intelligence.models import ProductIdentity
import product_intelligence.media_workflow as workflow


def _id(**extra):
    return ProductIdentity(mpn="ABC123", brand="Brand", model="Model One", **extra)


def test_manual_urls_before_search_and_deduplicated(monkeypatch, tmp_path):
    seen=[]
    monkeypatch.setattr(workflow,"search_web",lambda *_a,**_k:[SimpleNamespace(url="https://official/model",likely_official=True)])
    monkeypatch.setattr(workflow,"fetch_page",lambda u,**_k: seen.append(u) or SimpleNamespace(final_url=u,html="ABC123 Brand Model One",network_resources=[],method="requests"))
    monkeypatch.setattr(workflow,"discover_media",lambda *_a,**_k:[])
    workflow.run_media_product(_id(),tmp_path,manual_urls=["https://manual/model"],auto_search=True)
    assert seen==["https://manual/model","https://official/model"]


def test_fetch_is_request_first_and_relaxes_only_color(monkeypatch,tmp_path):
    captured={}
    monkeypatch.setattr(workflow,"search_web",lambda *_a,**_k:[])
    def fetch(u,**kwargs):
        captured["kwargs"]=kwargs
        return SimpleNamespace(final_url=u,html="ABC123 Brand Model One 256 GB",network_resources=[],method="requests")
    def discover(_h,_u,expected,**_kwargs):
        captured["expected"]=expected
        return [{"url":"https://cdn.example/full.jpg","media_type":"image","scope":"EXACT_PRODUCT","confidence":.96,"role":"product_gallery"}]
    monkeypatch.setattr(workflow,"fetch_page",fetch)
    monkeypatch.setattr(workflow,"discover_media",discover)
    monkeypatch.setattr(workflow,"download_media_item",lambda item,*_a,**_k:{**item,"downloaded":True})
    monkeypatch.setattr(workflow,"write_media_metadata",lambda *_a,**_k:None)
    rows=workflow.run_media_product(_id(color="Black",capacity="256 GB"),tmp_path,manual_urls=["https://brand.example/model"],auto_search=False)
    assert captured["kwargs"]["activate_lazy_media"] is True
    assert captured["kwargs"].get("prefer_browser",False) is False
    assert captured["expected"].color is None and captured["expected"].capacity=="256 GB"
    assert rows


def test_wrong_product_is_rejected_before_media(monkeypatch,tmp_path):
    called=[]
    monkeypatch.setattr(workflow,"search_web",lambda *_a,**_k:[])
    monkeypatch.setattr(workflow,"fetch_page",lambda u,**_k:SimpleNamespace(final_url=u,html="Different XYZ999",network_resources=[],method="requests"))
    monkeypatch.setattr(workflow,"discover_media",lambda *_a,**_k:called.append(1) or [])
    assert workflow.run_media_product(_id(),tmp_path,manual_urls=["https://wrong/item"],auto_search=False)==[]
    assert not called


def test_hosted_video_kept_as_metadata(monkeypatch,tmp_path):
    monkeypatch.setattr(workflow,"search_web",lambda *_a,**_k:[])
    monkeypatch.setattr(workflow,"fetch_page",lambda u,**_k:SimpleNamespace(final_url=u,html="ABC123 Brand Model One",network_resources=[],method="requests"))
    monkeypatch.setattr(workflow,"discover_media",lambda *_a,**_k:[{"url":"https://youtube.com/embed/demo","media_type":"video","scope":"EXACT_PRODUCT","confidence":.95,"role":"product_video"}])
    monkeypatch.setattr(workflow,"download_media_item",lambda item,*_a,**_k:{**item,"metadata_only":True,"downloaded":False})
    monkeypatch.setattr(workflow,"write_media_metadata",lambda *_a,**_k:None)
    assert workflow.run_media_product(_id(),tmp_path,manual_urls=["https://brand/model"],auto_search=False)[0]["metadata_only"] is True
