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


def test_targeted_peru_discovery_retries_with_product_page_hints(monkeypatch):
    seen = []

    def fake_query(identity, query, limit=6, timeout=12):
        seen.append(query)
        if "falabella.com.pe/falabella-pe/product" in query:
            return ["https://www.falabella.com.pe/falabella-pe/product/121511774/Audifonos-Gamer-JBL-Quantum-350-Wireless-Negro-JBLQ350WLBLKAM/121511775"]
        if "simple.ripley.com.pe" in query and "pmp" in query.lower():
            return ["https://simple.ripley.com.pe/audifonos-gamer-inalambricos-quantum-350-wireless-jblq350wlblkam-pmp00003308882"]
        return []

    monkeypatch.setattr("product_intelligence.price_discovery.search_web_query", fake_query)
    urls = discover_targeted_peru_sources(_identity(), limit_per_domain=3)
    assert any("falabella.com.pe/falabella-pe/product" in q for q in seen)
    assert any("simple.ripley.com.pe" in q and "pmp" in q.lower() for q in seen)
    assert any("falabella.com.pe/falabella-pe/product" in u for u in urls)
    assert any("pmp00003308882" in u for u in urls)


def test_targeted_peru_discovery_rejects_category_pages_even_if_they_mention_mpn(monkeypatch):
    def fake_query(identity, query, limit=6, timeout=12):
        if "falabella.com.pe" in query:
            return [
                "https://linio.falabella.com.pe/linio-pe/category/cat12940610/Audifonos-gamer?f.product.brandName=jbl",
                "https://www.falabella.com.pe/falabella-pe/product/121511774/Audifonos-Gamer-JBL-Quantum-350-Wireless-Negro-JBLQ350WLBLKAM/121511775",
            ]
        if "simple.ripley.com.pe" in query:
            return [
                "https://simple.ripley.com.pe/tecnologia/computacion-gamer/audifonos-gamer",
                "https://simple.ripley.com.pe/audifonos-gamer-inalambricos-quantum-350-wireless-jblq350wlblkam-pmp00003308882",
            ]
        return []

    monkeypatch.setattr("product_intelligence.price_discovery.search_web_query", fake_query)
    urls = discover_targeted_peru_sources(_identity(), limit_per_domain=4)
    assert not any("/category/" in u for u in urls)
    assert not any("/tecnologia/computacion-gamer/audifonos-gamer" in u for u in urls)
    assert any("/product/" in u for u in urls if "falabella.com.pe" in u)
    assert any("pmp00003308882" in u for u in urls if "ripley.com.pe" in u)


def test_category_page_cannot_be_accepted_as_price_offer():
    html = """
    <html><head><title>Audífonos gamer JBL | Linio Perú</title></head>
    <body>JBLQ350WLBLKAM JBL Quantum 350 Wireless S/ 699.90</body></html>
    """
    rows = extract_page_offers(
        html,
        "https://linio.falabella.com.pe/linio-pe/category/cat12940610/Audifonos-gamer?f.product.brandName=jbl",
        _identity(),
        channel="Falabella",
    )
    assert rows == []


def test_sodimac_coupon_only_is_not_treated_as_product_price():
    html = """
    <html><head><title>Audifonos Gamer JBL Quantum 350 Wireless Negro JBLQ350WLBLKAM | Sodimac Perú</title></head>
    <body>
      <h1>Audifonos Gamer JBL Quantum 350 Wireless Negro JBLQ350WLBLKAM</h1>
      <div>Vendido por technopshops</div>
      <div>TECHNOSHOPS PERU S.A.C.</div><div>RUC 20605145486</div>
      <div>Abre tu CMR y ahorra S/100</div>
    </body></html>
    """
    rows = extract_page_offers(
        html,
        "https://www.sodimac.com.pe/sodimac-pe/articulo/121511774/Audifonos-Gamer-JBL-Quantum-350-Wireless-Negro-JBLQ350WLBLKAM/121511775",
        _identity(),
        channel="Sodimac",
    )
    assert rows == []


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
