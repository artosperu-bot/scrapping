from __future__ import annotations

from .workspaces import RunStatus, Stage, WorkspaceRepository


class WorkspaceService:
    """Resume/orchestration boundary around persistent workspace state."""

    def __init__(self, repository: WorkspaceRepository):
        self.repository = repository

    def recover_interrupted_runs(self) -> int:
        return self.repository.recover_running_stages()

    def next_stage(self, run_id: str) -> Stage | None:
        states = self.repository.list_stage_states(run_id)
        for stage in Stage:
            state = states.get(stage)
            if state is None or state.status is not RunStatus.COMPLETED:
                return stage
        return None
