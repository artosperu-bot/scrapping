from product_intelligence.models import ProductIdentity
from product_intelligence.price_discovery import extract_page_offers, discover_targeted_peru_sources


def _identity():
    return ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")


def test_targeted_peru_discovery_queries_priority_domains(monkeypatch):
    seen = []

    def fake_query(identity, query, limit=6, timeout=12):
        seen.append(query)
        if "falabella.com.pe" in query:
            return ["https://www.falabella.com.pe/falabella-pe/product/121511774/x/121511775"]
        if "simple.ripley.com.pe" in query:
            return ["https://simple.ripley.com.pe/audifonos-gamer-jblq350wlblkam-pmp00003308882"]
        return []

    monkeypatch.setattr("product_intelligence.price_discovery.search_web_query", fake_query)
    urls = discover_targeted_peru_sources(_identity(), limit_per_domain=3)

    assert any("site:falabella.com.pe" in q for q in seen)
    assert any("site:simple.ripley.com.pe" in q for q in seen)
    assert urls[0].startswith("https://www.falabella.com.pe/")
    assert any("simple.ripley.com.pe" in u for u in urls)


def test_extract_falabella_marketplace_offer_with_seller_and_legal_identity():
    html = """
    <html><head><title>Audifonos Gamer JBL Quantum 350 Wireless JBLQ350WLBLKAM</title></head>
    <body>
      <h1>Audifonos Gamer JBL Quantum 350 Wireless Negro JBLQ350WLBLKAM</h1>
      <div>Vendido por technopshops</div>
      <div>TECHNOSHOPS PERU S.A.C.</div>
      <div>RUC 20605145486</div>
      <div>S/ 299</div><div>S/ 499</div>
      <div>Modelo Quantum 350</div>
    </body></html>
    """
    rows = extract_page_offers(html, "https://www.falabella.com.pe/falabella-pe/product/121511774/x/121511775", _identity(), channel="Falabella")
    assert len(rows) == 1
    row = rows[0]
    assert row.selling_price == 299
    assert row.list_price == 499
    assert row.seller_display_name.lower() == "technopshops"
    assert (row.seller_legal_name or "").rstrip(".") == "TECHNOSHOPS PERU S.A.C"
    assert row.seller_tax_id == "20605145486"
    assert row.confidence >= 0.95


def test_extract_ripley_marketplace_offer_prefers_internet_price_and_seller():
    html = """
    <html><head><title>AUDIFONOS GAMER INALAMBRICOS QUANTUM 350 WIRELESS JBLQ350WLBLKAM</title></head>
    <body>
      <h1>AUDIFONOS GAMER INALAMBRICOS QUANTUM 350 WIRELESS JBLQ350WLBLKAM</h1>
      <div>Vendido por: TECHNOSHOPS</div>
      <div>Normal S/ 569.00</div>
      <div>Internet S/ 315.00 -45%</div>
      <div>Modelo Quantum 350</div>
    </body></html>
    """
    rows = extract_page_offers(html, "https://simple.ripley.com.pe/audifonos-gamer-jblq350wlblkam-pmp00003308882", _identity(), channel="Ripley")
    assert len(rows) == 1
    row = rows[0]
    assert row.selling_price == 315
    assert row.list_price == 569
    assert row.seller_display_name == "TECHNOSHOPS"
    assert row.currency == "PEN"
    assert row.confidence >= 0.95
