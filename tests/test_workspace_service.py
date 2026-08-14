from product_intelligence.workspace_service import WorkspaceService
from product_intelligence.workspaces import RunStatus, Stage, WorkspaceRepository


def _new_run(repo):
    workspace = repo.create_workspace("Trabajo")
    product = repo.add_product(workspace.id, part_number="PN-1")
    return repo.create_run(product.id)


def test_recovery_resets_only_interrupted_running_stage(tmp_path):
    repo = WorkspaceRepository(tmp_path / "workspaces.db")
    run = _new_run(repo)
    repo.set_stage_status(run.id, Stage.IDENTITY, RunStatus.COMPLETED)
    repo.set_stage_status(run.id, Stage.EVIDENCE, RunStatus.RUNNING)
    service = WorkspaceService(repo)

    changed = service.recover_interrupted_runs()
    states = repo.list_stage_states(run.id)

    assert changed == 1
    assert states[Stage.IDENTITY].status is RunStatus.COMPLETED
    assert states[Stage.EVIDENCE].status is RunStatus.PENDING


def test_next_stage_skips_completed_stages(tmp_path):
    repo = WorkspaceRepository(tmp_path / "workspaces.db")
    run = _new_run(repo)
    repo.set_stage_status(run.id, Stage.IDENTITY, RunStatus.COMPLETED)
    repo.set_stage_status(run.id, Stage.EVIDENCE, RunStatus.COMPLETED)
    service = WorkspaceService(repo)

    assert service.next_stage(run.id) is Stage.PDFS


def test_next_stage_returns_none_when_run_is_complete(tmp_path):
    repo = WorkspaceRepository(tmp_path / "workspaces.db")
    run = _new_run(repo)
    for stage in Stage:
        repo.set_stage_status(run.id, stage, RunStatus.COMPLETED)

    assert WorkspaceService(repo).next_stage(run.id) is None
