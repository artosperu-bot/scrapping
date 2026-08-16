from __future__ import annotations

import json
from pathlib import Path

from .price_models import PriceOffer


def _base(output_root: str | Path) -> Path:
    path = Path(output_root) / "price_intelligence"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _latest_key(row: dict) -> tuple:
    return (
        str(row.get("part_number") or row.get("model") or "").casefold(),
        str(row.get("channel") or "").casefold(),
        str(row.get("seller_display_name") or "").casefold(),
        str(row.get("publication_id") or row.get("sku") or row.get("url") or "").casefold(),
    )


def _identity_source_key(identity) -> str:
    for field in ("mpn", "ean", "upc", "gtin", "model", "product_name"):
        value = str(getattr(identity, field, None) or "").strip().casefold()
        if value:
            return f"{field}:{value}"
    return ""


def _source_registry_path(output_root: str | Path) -> Path:
    return _base(output_root) / "source_bindings.json"


def _load_source_registry(output_root: str | Path) -> dict:
    path = _source_registry_path(output_root)
    if not path.exists():
        return {"version": 1, "products": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "products": {}}
    if not isinstance(data, dict) or not isinstance(data.get("products"), dict):
        return {"version": 1, "products": {}}
    return {"version": 1, "products": data["products"]}


def load_validated_source_urls(output_root: str | Path, identity) -> list[str]:
    key = _identity_source_key(identity)
    if not key:
        return []
    registry = _load_source_registry(output_root)
    rows = registry["products"].get(key, [])
    if not isinstance(rows, list):
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def save_validated_source_bindings(output_root: str | Path, identity, offers: list[PriceOffer]) -> None:
    key = _identity_source_key(identity)
    if not key:
        return
    strong_rows = []
    for offer in offers:
        match = str(offer.identity_match or "").strip().upper()
        url = str(offer.url or "").strip()
        if not url or not (match.startswith("EXACT_") or match == "BRAND_MODEL"):
            continue
        row = offer.to_dict()
        strong_rows.append(
            {
                "url": url,
                "channel": row.get("channel"),
                "identity_match": match,
                "last_seen": row.get("observed_at"),
            }
        )
    if not strong_rows:
        return

    registry = _load_source_registry(output_root)
    products = registry["products"]
    existing = products.get(key, [])
    merged: dict[str, dict] = {}
    if isinstance(existing, list):
        for row in existing:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            if url:
                merged[url] = row
    for row in strong_rows:
        merged[row["url"]] = row
    products[key] = list(merged.values())

    path = _source_registry_path(output_root)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def save_price_run(output_root: str | Path, offers: list[PriceOffer]) -> None:
    base = _base(output_root)
    rows = [o.to_dict() for o in offers]

    existing = load_latest(output_root)
    merged: dict[tuple, dict] = {_latest_key(row): row for row in existing if isinstance(row, dict)}
    touched_products = {str(row.get("part_number") or row.get("model") or "").casefold() for row in rows}
    if touched_products:
        merged = {key: row for key, row in merged.items() if key[0] not in touched_products}
    for row in rows:
        merged[_latest_key(row)] = row
    latest_rows = sorted(merged.values(), key=lambda row: (str(row.get("part_number") or row.get("model") or ""), float(row.get("selling_price") or 0)))

    tmp = base / "latest.json.tmp"
    tmp.write_text(json.dumps(latest_rows, ensure_ascii=False, indent=2), encoding="utf-8")
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


def save_channel_coverage(output_root: str | Path, report: dict) -> Path:
    path = _base(output_root) / "channel_coverage.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_latest(output_root: str | Path) -> list[dict]:
    path = _base(output_root) / "latest.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []
