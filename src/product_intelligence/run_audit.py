from __future__ import annotations

from datetime import datetime, timezone


def part_number_from_event(event: dict) -> str:
    identity = event.get("identity") or {}
    return str(event.get("part_number") or identity.get("mpn") or identity.get("ean") or identity.get("upc") or identity.get("gtin") or identity.get("model") or "-")


def normalize_event(module: str, event: dict) -> dict:
    kind = str(event.get("type") or "event")
    raw_status = str(event.get("status") or kind).upper()
    if kind in {"media", "offer"}:
        status = "FOUND"
    elif kind in {"media_filtered", "media_rejected"} or raw_status == "REJECTED_IDENTITY":
        status = "REJECTED"
    elif kind in {"error", "fatal"}:
        status = "ERROR"
    elif kind in {"done", "batch_done"}:
        status = "DONE"
    else:
        status = raw_status
    item = event.get("item") or event.get("offer") or {}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "part_number": part_number_from_event(event),
        "module": str(module).upper(),
        "source": event.get("source") or event.get("channel") or item.get("channel") or item.get("source") or "",
        "url": event.get("url") or item.get("url") or "",
        "status": status,
        "detail": event.get("message") or event.get("reason") or event.get("error") or kind,
        "result": item,
    }


def format_event(module: str, event: dict) -> str:
    row = normalize_event(module, event)
    source = f" [{row['source']}]" if row["source"] else ""
    url = f" {row['url']}" if row["url"] else ""
    return f"[{row['module']}] {row['part_number']} · {row['status']}{source} · {row['detail']}{url}"
