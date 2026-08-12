from __future__ import annotations

import json
from pathlib import Path

from .price_models import PriceOffer


def _base(output_root: str | Path) -> Path:
    path = Path(output_root) / "price_intelligence"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_price_run(output_root: str | Path, offers: list[PriceOffer]) -> None:
    base = _base(output_root)
    rows = [o.to_dict() for o in offers]

    tmp = base / "latest.json.tmp"
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(base / "latest.json")

    with (base / "history.jsonl").open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    sellers: dict[str, dict] = {}
    sellers_path = base / "sellers.json"
    if sellers_path.exists():
        try:
            loaded = json.loads(sellers_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                sellers.update(loaded)
        except Exception:
            pass
    for row in rows:
        name = str(row.get("seller_display_name") or "").strip()
        if not name:
            continue
        key = name.casefold()
        sellers[key] = {
            "display_name": name,
            "legal_name": row.get("seller_legal_name"),
            "tax_id": row.get("seller_tax_id"),
            "channel": row.get("channel"),
            "last_seen": row.get("observed_at"),
        }
    sellers_path.write_text(json.dumps(sellers, ensure_ascii=False, indent=2), encoding="utf-8")


def load_latest(output_root: str | Path) -> list[dict]:
    path = _base(output_root) / "latest.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []
