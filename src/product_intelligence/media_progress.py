from __future__ import annotations

from dataclasses import dataclass

_STAGE_PERCENT = {
    "queued": 0,
    "searching": 15,
    "validating": 30,
    "extracting": 50,
    "downloading": 75,
    "finalizing": 90,
    "done": 100,
    "error": 100,
}


def stage_percent(stage: str) -> int:
    return int(_STAGE_PERCENT.get(str(stage or "queued").lower(), 0))


@dataclass
class BatchProgress:
    total: int
    completed: int = 0
    current_index: int | None = None
    current_label: str = ""
    current_stage: str = "queued"
    downloaded: int = 0
    metadata_only: int = 0
    errors: int = 0

    def start_product(self, index: int, label: str) -> None:
        self.current_index = int(index)
        self.current_label = str(label or f"Producto {index + 1}")
        self.current_stage = "searching"

    def set_stage(self, stage: str) -> None:
        self.current_stage = str(stage or "queued").lower()

    def finish_product(self, *, downloaded: int = 0, metadata_only: int = 0, error: bool = False) -> None:
        self.downloaded += int(downloaded or 0)
        self.metadata_only += int(metadata_only or 0)
        if error:
            self.errors += 1
        self.completed = min(max(self.total, 0), self.completed + 1)
        self.current_stage = "error" if error else "done"

    @property
    def product_percent(self) -> int:
        return stage_percent(self.current_stage)

    @property
    def overall_percent(self) -> int:
        if self.total <= 0:
            return 0
        if self.completed >= self.total:
            return 100
        current_fraction = 0.0
        if self.current_index is not None and self.current_stage not in {"done", "error"}:
            current_fraction = self.product_percent / 100.0
        value = ((self.completed + current_fraction) / self.total) * 100.0
        return max(0, min(99, int(round(value))))
