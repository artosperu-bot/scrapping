from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock


@dataclass(frozen=True)
class AuditEvent:
    timestamp: str
    run_id: str
    process_type: str
    product_id: str = ""
    stage: str = ""
    source: str = ""
    url: str = ""
    status: str = "PROGRESS"
    detail: str = ""
    result: str = ""

    @classmethod
    def create(cls, run_id: str, process_type: str, **kwargs) -> "AuditEvent":
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_id=str(run_id),
            process_type=str(process_type).upper(),
            product_id=str(kwargs.get("product_id") or ""),
            stage=str(kwargs.get("stage") or ""),
            source=str(kwargs.get("source") or ""),
            url=str(kwargs.get("url") or ""),
            status=str(kwargs.get("status") or "PROGRESS").upper(),
            detail=str(kwargs.get("detail") or ""),
            result=str(kwargs.get("result") or ""),
        )


class AuditSink:
    def __init__(self):
        self._items: list[AuditEvent] = []
        self._lock = Lock()

    def emit(self, event: AuditEvent) -> None:
        with self._lock:
            self._items.append(event)

    def events(self) -> list[AuditEvent]:
        with self._lock:
            return list(self._items)


def filter_events(events, *, process_type: str | None = None, status: str | None = None, query: str | None = None):
    process = str(process_type or "").upper()
    wanted_status = str(status or "").upper()
    needle = str(query or "").strip().lower()
    out = []
    for event in events:
        if process and event.process_type != process:
            continue
        if wanted_status and event.status != wanted_status:
            continue
        if needle:
            haystack = " ".join((event.run_id, event.product_id, event.stage, event.source, event.url, event.status, event.detail, event.result)).lower()
            if needle not in haystack:
                continue
        out.append(event)
    return out
