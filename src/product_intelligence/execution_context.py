from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from threading import Lock
from typing import Any

_seq = count(1)
_seq_lock = Lock()


def new_run_id(process_type: str) -> str:
    kind = str(process_type or "RUN").upper()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    with _seq_lock:
        suffix = next(_seq)
    return f"{kind}-{stamp}-{suffix:04d}"


@dataclass(frozen=True)
class ProductSnapshot:
    index: int
    label: str
    identity: Any
    manual_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionSnapshot:
    run_id: str
    process_type: str
    started_at: str
    output_root: str
    products: tuple[ProductSnapshot, ...]
    workbook: str = ""
    overwrite: bool = False
    options: tuple[tuple[str, Any], ...] = ()

    @classmethod
    def create(
        cls,
        process_type: str,
        output_root: str,
        products: list[ProductSnapshot] | tuple[ProductSnapshot, ...],
        *,
        workbook: str = "",
        overwrite: bool = False,
        options: dict[str, Any] | None = None,
    ) -> "ExecutionSnapshot":
        kind = str(process_type).upper()
        return cls(
            run_id=new_run_id(kind),
            process_type=kind,
            started_at=datetime.now(timezone.utc).isoformat(),
            output_root=str(output_root),
            products=tuple(products),
            workbook=str(workbook),
            overwrite=bool(overwrite),
            options=tuple(sorted((options or {}).items())),
        )

    def option(self, name: str, default: Any = None) -> Any:
        return dict(self.options).get(name, default)
