from __future__ import annotations

from .workspaces import RunStatus, Stage, WorkspaceRepository


class WorkspaceRunTracker:
    """Tracks stage checkpoints without owning or duplicating any processing engine."""

    CORE_COMPLETION_STAGES = (
        Stage.EVIDENCE,
        Stage.PDFS,
        Stage.CANONICAL,
        Stage.EXCEL,
    )

    def __init__(self, repository: WorkspaceRepository, workspace_id: str):
        self.repository = repository
        self.workspace_id = workspace_id
        self._active: dict[Stage, list[str]] = {}

    def _ensure_run(self, product_id: str) -> str:
        owned_product_ids = {product.id for product in self.repository.list_products(self.workspace_id)}
        if product_id not in owned_product_ids:
            raise ValueError(f"product {product_id} does not belong to workspace {self.workspace_id}")
        run = self.repository.latest_run(product_id)
        if run is None or run.status is RunStatus.COMPLETED:
            run = self.repository.create_run(product_id)
        return run.id

    def begin_core(self, product_ids: list[str]) -> None:
        run_ids: list[str] = []
        for product_id in product_ids:
            run_id = self._ensure_run(product_id)
            self.repository.set_stage_status(run_id, Stage.IDENTITY, RunStatus.COMPLETED)
            self.repository.set_stage_status(run_id, Stage.EVIDENCE, RunStatus.RUNNING)
            run_ids.append(run_id)
        self._active[Stage.EVIDENCE] = run_ids

    def finish_core(self, *, success: bool, error: str | None = None) -> None:
        run_ids = self._active.pop(Stage.EVIDENCE, [])
        if success:
            for run_id in run_ids:
                for stage in self.CORE_COMPLETION_STAGES:
                    self.repository.set_stage_status(run_id, stage, RunStatus.COMPLETED)
        else:
            for run_id in run_ids:
                self.repository.set_stage_status(run_id, Stage.EVIDENCE, RunStatus.ERROR, error=error)

    def begin_stage(self, product_ids: list[str], stage: Stage) -> None:
        if stage in (Stage.IDENTITY, Stage.EVIDENCE, Stage.PDFS, Stage.CANONICAL, Stage.EXCEL):
            raise ValueError(f"use begin_core for {stage.value}")
        run_ids: list[str] = []
        for product_id in product_ids:
            run_id = self._ensure_run(product_id)
            self.repository.set_stage_status(run_id, stage, RunStatus.RUNNING)
            run_ids.append(run_id)
        self._active[stage] = run_ids

    def finish_stage(self, stage: Stage, *, success: bool, error: str | None = None) -> None:
        run_ids = self._active.pop(stage, [])
        status = RunStatus.COMPLETED if success else RunStatus.ERROR
        for run_id in run_ids:
            self.repository.set_stage_status(run_id, stage, status, error=None if success else error)

    def has_active(self, stage: Stage) -> bool:
        return bool(self._active.get(stage))
