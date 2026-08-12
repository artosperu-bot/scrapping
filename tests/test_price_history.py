import json
from pathlib import Path

from product_intelligence.price_history import load_latest, save_price_run
from product_intelligence.price_models import PriceOffer


def offer(price=299.0, seller="technopshops"):
    return PriceOffer(part_number="JBLQ350WLBLKAM", brand="JBL", model="Quantum 350 Wireless", channel="Falabella", seller_display_name=seller, selling_price=price, currency="PEN", url="https://example.com/p/1", confidence=1.0, identity_match="EXACT_MPN", source_type="api", source_method="json")


def test_save_price_run_writes_latest_history_and_sellers(tmp_path):
    save_price_run(tmp_path, [offer()])
    save_price_run(tmp_path, [offer(289.0)])
    base = tmp_path / "price_intelligence"
    assert (base / "latest.json").exists()
    assert (base / "history.jsonl").exists()
    assert (base / "sellers.json").exists()
    lines = (base / "history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[-1])["selling_price"] == 289.0
    latest = load_latest(tmp_path)
    assert latest[0]["selling_price"] == 289.0
