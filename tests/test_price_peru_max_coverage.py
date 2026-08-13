from urllib.parse import unquote_plus

from product_intelligence.models import ProductIdentity
from product_intelligence import price_identity, price_peru_coverage, price_workflow
from product_intelligence.price_adapters import parse_vtex_payload
from product_intelligence.price_models import PriceOffer

IDENTITY = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")


def test_vtex_accepts_exact_mpn_from_item_reference_and_keeps_distinct_publications():
    payload = [
        {"productId":"1001","productName":"Audifonos JBL Quantum 350 Wireless","brand":"JBL","link":"/oferta-a/p","items":[{"itemId":"sku-a","referenceId":[{"Key":"RefId","Value":"JBLQ350WLBLKAM"}],"sellers":[{"sellerId":"pv","sellerName":"Plaza Vea","commertialOffer":{"Price":469,"ListPrice":499,"AvailableQuantity":0}}]}]},
        {"productId":"1002","productName":"Audifonos Gamer Quantum 350 Wireless","brand":"JBL","link":"/oferta-b/p","items":[{"itemId":"sku-b","referenceId":[{"Key":"RefId","Value":"JBLQ350WLBLKAM"}],"sellers":[{"sellerId":"aliadas","sellerName":"Marcas Aliadas","commertialOffer":{"Price":329,"ListPrice":399,"AvailableQuantity":2}}]}]},
    ]
    rows = parse_vtex_payload(payload, IDENTITY, channel="PlazaVea", source_url="https://www.plazavea.com.pe")
    assert {(r.publication_id, r.seller_display_name, r.selling_price) for r in rows} == {("1001","Plaza Vea",469.0),("1002","Marcas Aliadas",329.0)}


def test_targeted_discovery_covers_all_supported_peru_marketplaces(monkeypatch):
    expected = {"falabella.com.pe","simple.ripley.com.pe","mercadolibre.com.pe","plazavea.com.pe","oechsle.pe","sodimac.com.pe","jbl.com.pe"}
    assert expected.issubset(set(price_peru_coverage.PERU_MARKETPLACE_DOMAINS))
    seen = []
    monkeypatch.setattr(price_peru_coverage, "search_web_query", lambda _i, q, **_k: seen.append(q) or [])
    price_peru_coverage.discover_additional_peru_pdps(IDENTITY, limit_per_domain=4)
    for domain in expected:
        assert any(f"site:{domain}" in q for q in seen)


def test_vtex_direct_probe_requests_wide_result_window(monkeypatch):
    captured = {}
    class Response:
        status_code = 200
        def json(self): return []
    monkeypatch.setattr(price_workflow.requests, "get", lambda url, **_k: captured.setdefault("url", url) and Response())
    price_workflow._try_vtex("https://www.plazavea.com.pe", IDENTITY, "PlazaVea")
    assert "_from=0" in captured["url"] and "_to=49" in captured["url"]


def test_targeted_discovery_preserves_multiple_pdp_urls_from_same_marketplace(monkeypatch):
    urls = [
        "https://www.falabella.com.pe/falabella-pe/product/1/jblq350wlblkam/11",
        "https://www.falabella.com.pe/falabella-pe/product/2/jblq350wlblkam/22",
        "https://www.falabella.com.pe/falabella-pe/product/3/jblq350wlblkam/33",
    ]
    monkeypatch.setattr(price_peru_coverage, "search_web_query", lambda _i, q, **_k: urls if "falabella.com.pe" in q else [])
    assert price_peru_coverage.discover_additional_peru_pdps(IDENTITY, limit_per_domain=5, domains=("falabella.com.pe",)) == urls


def test_mercadolibre_tries_exact_part_number_and_model_queries(monkeypatch):
    requested = []
    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload
    def fake_get(url, **_kwargs):
        decoded = unquote_plus(url)
        requested.append(decoded)
        if "q=JBL Quantum 350 Wireless" in decoded:
            return Response({"results":[{"id":"MPE-2","title":"JBL Quantum 350 Wireless","price":319,"currency_id":"PEN","permalink":"https://www.mercadolibre.com.pe/q350-2","attributes":[{"id":"BRAND","value_name":"JBL"},{"id":"MODEL","value_name":"Quantum 350 Wireless"},{"id":"MPN","value_name":"JBLQ350WLBLKAM"}]}]})
        return Response({"results":[]})
    monkeypatch.setattr(price_workflow.requests, "get", fake_get)
    rows = price_workflow._try_mercadolibre(IDENTITY)
    assert any("q=JBLQ350WLBLKAM" in u for u in requested)
    assert any("q=JBL Quantum 350 Wireless" in u for u in requested)
    assert len(rows) == 1 and rows[0].publication_id == "MPE-2"


def test_general_peru_retail_discovery_finds_exact_mpn_beyond_big_marketplaces(monkeypatch):
    discovered = [
        "https://www.infiniti.com.pe/shop/jblq350wlblkam-producto-9016",
        "https://www.perudataconsult.net/products/audifono-jblq350wlblkam",
        "https://arteus.pe/products/jbl-jblq350wlblkam-quantum-350",
        "https://baetech.pe/products/jbl-quantum-350-jblq350wlblkam",
        "https://www.panacompu.com/peru/es/informacion-producto/jbl-quantum-350",
        "https://example.cl/products/jblq350wlblkam",
        "https://tienda.com.pe/category/audifonos",
    ]
    seen_queries = []

    def fake_search(_identity, query, **_kwargs):
        seen_queries.append(query)
        return discovered

    monkeypatch.setattr(price_peru_coverage, "search_web_query", fake_search)
    rows = price_peru_coverage.discover_general_peru_retailers(IDENTITY, limit=10)

    assert "https://www.infiniti.com.pe/shop/jblq350wlblkam-producto-9016" in rows
    assert "https://www.perudataconsult.net/products/audifono-jblq350wlblkam" in rows
    assert "https://arteus.pe/products/jbl-jblq350wlblkam-quantum-350" in rows
    assert "https://baetech.pe/products/jbl-quantum-350-jblq350wlblkam" in rows
    assert "https://www.panacompu.com/peru/es/informacion-producto/jbl-quantum-350" in rows
    assert not any("example.cl" in row or "/category/" in row for row in rows)
    assert any('"JBLQ350WLBLKAM"' in query and "precio" in query.lower() for query in seen_queries)


def test_known_peru_retail_seed_domains_are_queried_by_exact_part_number(monkeypatch):
    seen_queries = []
    monkeypatch.setattr(price_peru_coverage, "search_web_query", lambda _i, query, **_k: seen_queries.append(query) or [])
    price_peru_coverage.discover_general_peru_retailers(IDENTITY, limit=10)
    for domain in price_peru_coverage.PERU_RETAIL_HINT_DOMAINS:
        assert any(f"site:{domain}" in query and "JBLQ350WLBLKAM" in query for query in seen_queries)


def test_non_pe_domain_can_be_peru_market_when_domain_or_path_is_explicitly_peru():
    peru_data = PriceOffer(
        part_number="JBLQ350WLBLKAM", brand="JBL", model="Quantum 350 Wireless",
        channel="Peru Data", seller_display_name="Peru Data", selling_price=359,
        currency="PEN", url="https://www.perudataconsult.net/products/audifono-jblq350wlblkam",
        confidence=1.0, identity_match="EXACT_MPN", source_type="structured", source_method="jsonld",
    )
    pana = PriceOffer(
        part_number="JBLQ350WLBLKAM", brand="JBL", model="Quantum 350 Wireless",
        channel="Pana Compu", seller_display_name="Pana Compu", selling_price=302.07,
        currency="PEN", url="https://www.panacompu.com/peru/es/informacion-producto/jbl-quantum-350",
        confidence=1.0, identity_match="EXACT_MPN", source_type="structured", source_method="jsonld",
    )
    foreign = PriceOffer(
        part_number="JBLQ350WLBLKAM", brand="JBL", model="Quantum 350 Wireless",
        channel="Foreign", seller_display_name="Foreign", selling_price=99,
        currency="USD", url="https://shop.example.com/products/jblq350wlblkam",
        confidence=1.0, identity_match="EXACT_MPN", source_type="structured", source_method="jsonld",
    )
    assert price_identity.is_peru_offer(peru_data)
    assert price_identity.is_peru_offer(pana)
    assert not price_identity.is_peru_offer(foreign)
