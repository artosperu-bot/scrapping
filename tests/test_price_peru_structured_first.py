from __future__ import annotations

from types import SimpleNamespace
from product_intelligence.models import ProductIdentity
from product_intelligence.price_adapters import parse_vtex_payload
from product_intelligence.price_identity import dedupe_offers
from product_intelligence.price_models import PriceOffer
from product_intelligence import price_peru_coverage, price_workflow

PLAZAVEA_EXACT_PAYLOAD=[{"productId":"100488604","productName":"Audífonos Over Ear JBL JBLQ350WLBLKAM Negro","brand":"JBL","productReference":"20283591","link":"https://www.plazavea.com.pe/audifonos-over-ear-jbl-jblq350wlblkam-negro/p","Modelo":["JBLQ350WLBLKAM"],"items":[{"itemId":"10696064","ean":"6925281986505","sellers":[{"sellerId":"1","sellerName":"Plaza Vea","commertialOffer":{"Price":469.0,"ListPrice":469.0,"AvailableQuantity":0,"IsAvailable":False}}]}]}]

def _identity(): return ProductIdentity(brand="JBL",model="JBLQ350WLBLKAM",mpn="JBLQ350WLBLKAM")

def test_vtex_parser_prefers_exact_product_link_and_keeps_out_of_stock_price():
    rows=parse_vtex_payload(PLAZAVEA_EXACT_PAYLOAD,_identity(),channel="PlazaVea",source_url="https://www.plazavea.com.pe")
    assert len(rows)==1
    row=rows[0]
    assert row.channel=="PlazaVea" and row.seller_display_name=="Plaza Vea"
    assert row.selling_price==469.0 and row.stock==0 and row.availability=="unavailable"
    assert row.url=="https://www.plazavea.com.pe/audifonos-over-ear-jbl-jblq350wlblkam-negro/p"
    assert row.confidence>=0.95

def test_run_price_product_probes_peru_structured_sources_even_when_web_discovery_is_empty(monkeypatch,tmp_path):
    class Response:
        status_code=200
        def raise_for_status(self): return None
        def json(self): return PLAZAVEA_EXACT_PAYLOAD
    requested=[]
    def fake_get(url,**_kwargs): requested.append(url); return Response()
    monkeypatch.setattr(price_workflow.requests,"get",fake_get)
    monkeypatch.setattr(price_workflow,"_try_mercadolibre",lambda _identity:[])
    monkeypatch.setattr(price_workflow,"discover_price_sources",lambda _identity,limit=12:[])
    monkeypatch.setattr(price_workflow,"discover_additional_peru_pdps",lambda *_a,**_k:[])
    monkeypatch.setattr(price_workflow,"discover_general_peru_retailers",lambda *_a,**_k:[])
    monkeypatch.setattr(price_workflow,"PERU_STRUCTURED_SOURCES",(("PlazaVea","https://www.plazavea.com.pe"),),raising=False)
    rows=price_workflow.run_price_product(_identity(),tmp_path)
    assert any("plazavea.com.pe/api/catalog_system/pub/products/search" in url for url in requested)
    assert len(rows)==1 and rows[0].channel=="PlazaVea" and rows[0].selling_price==469.0 and rows[0].currency=="PEN"

def test_peru_offer_is_displayed_before_foreign_fallback_even_when_foreign_numeric_price_is_lower():
    peru=PriceOffer(part_number="JBLQ350WLBLKAM",brand="JBL",model="JBLQ350WLBLKAM",channel="PlazaVea",seller_display_name="Plaza Vea",selling_price=469.0,currency="PEN",url="https://www.plazavea.com.pe/producto/p",confidence=1.0,identity_match="EXACT_MPN",source_type="api",source_method="vtex_catalog")
    foreign=PriceOffer(part_number="JBLQ350WLBLKAM",brand="JBL",model="JBLQ350WLBLKAM",channel="Tcsgrenada",seller_display_name="The Computer Store (Gda) Ltd.",selling_price=180.0,currency="XCD",url="https://tcsgrenada.net/product",confidence=1.0,identity_match="EXACT_MPN",source_type="web",source_method="jsonld")
    assert [row.channel for row in dedupe_offers([foreign,peru])]==["PlazaVea","Tcsgrenada"]

def test_general_retail_queries_cover_every_strong_identifier():
    identity=ProductIdentity(brand="JBL",model="Quantum 350 Wireless",mpn="JBLQ350WLBLKAM",ean="0050036382366",upc="050036382366")
    joined="\n".join(price_peru_coverage._general_retail_queries(identity))
    assert "JBLQ350WLBLKAM" in joined and "0050036382366" in joined and "050036382366" in joined

def test_price_workflow_runs_second_retail_discovery_pass_without_strong_id(monkeypatch,tmp_path):
    identity=ProductIdentity(brand="JBL",model="Quantum 350 Wireless",mpn="JBLQ350WLBLKAM")
    calls=[]
    def discover(search_identity,**_kwargs):
        calls.append(search_identity)
        return []
    monkeypatch.setattr(price_workflow,"PERU_STRUCTURED_SOURCES",())
    monkeypatch.setattr(price_workflow,"_try_mercadolibre",lambda *_a,**_k:[])
    monkeypatch.setattr(price_workflow,"discover_additional_peru_pdps",lambda *_a,**_k:[])
    monkeypatch.setattr(price_workflow,"discover_general_peru_retailers",discover)
    monkeypatch.setattr(price_workflow,"discover_price_sources",lambda *_a,**_k:[])
    monkeypatch.setattr(price_workflow,"save_price_run",lambda *_a,**_k:None)
    price_workflow.run_price_product(identity,tmp_path)
    assert any(call.mpn is None and call.model=="Quantum 350 Wireless" for call in calls)
