import pytest

from product_intelligence.workspace_tracking import WorkspaceRunTracker
from product_intelligence.workspaces import RunStatus, Stage, WorkspaceRepository


def _tracker(tmp_path):
    repo = WorkspaceRepository(tmp_path / "workspaces.db")
    workspace = repo.create_workspace("Falabella")
    p1 = repo.add_product(workspace.id, part_number="PN-1")
    p2 = repo.add_product(workspace.id, part_number="PN-2")
    return repo, WorkspaceRunTracker(repo, workspace.id), [p1, p2]


def test_core_checkpoint_marks_only_core_stages_complete(tmp_path):
    repo, tracker, products = _tracker(tmp_path)
    tracker.begin_core([p.id for p in products])
    tracker.finish_core(success=True)

    for product in products:
        run = repo.latest_run(product.id)
        states = repo.list_stage_states(run.id)
        assert states[Stage.IDENTITY].status is RunStatus.COMPLETED
        assert states[Stage.EVIDENCE].status is RunStatus.COMPLETED
        assert states[Stage.PDFS].status is RunStatus.COMPLETED
        assert states[Stage.CANONICAL].status is RunStatus.COMPLETED
        assert states[Stage.EXCEL].status is RunStatus.COMPLETED
        assert states[Stage.MULTIMEDIA].status is RunStatus.PENDING
        assert states[Stage.PRICES].status is RunStatus.PENDING


def test_independent_media_and_price_checkpoints_reuse_latest_run(tmp_path):
    repo, tracker, products = _tracker(tmp_path)
    tracker.begin_core([p.id for p in products])
    tracker.finish_core(success=True)
    original_runs = {p.id: repo.latest_run(p.id).id for p in products}

    tracker.begin_stage([products[0].id], Stage.MULTIMEDIA)
    tracker.finish_stage(Stage.MULTIMEDIA, success=True)
    tracker.begin_stage([products[0].id], Stage.PRICES)
    tracker.finish_stage(Stage.PRICES, success=True)

    run = repo.latest_run(products[0].id)
    states = repo.list_stage_states(run.id)
    assert run.id == original_runs[products[0].id]
    assert states[Stage.MULTIMEDIA].status is RunStatus.COMPLETED
    assert states[Stage.PRICES].status is RunStatus.COMPLETED
    assert repo.get_run(run.id).status is RunStatus.COMPLETED


def test_failed_stage_is_recorded_without_erasing_completed_stages(tmp_path):
    repo, tracker, products = _tracker(tmp_path)
    tracker.begin_core([products[0].id])
    tracker.finish_core(success=True)
    tracker.begin_stage([products[0].id], Stage.PRICES)
    tracker.finish_stage(Stage.PRICES, success=False, error="network")

    run = repo.latest_run(products[0].id)
    states = repo.list_stage_states(run.id)
    assert states[Stage.EXCEL].status is RunStatus.COMPLETED
    assert states[Stage.PRICES].status is RunStatus.ERROR
    assert repo.get_run(run.id).status is RunStatus.ERROR


def test_tracker_rejects_product_owned_by_another_workspace(tmp_path):
    repo = WorkspaceRepository(tmp_path / "workspaces.db")
    first = repo.create_workspace("Falabella")
    second = repo.create_workspace("Ripley")
    foreign_product = repo.add_product(second.id, part_number="PN-X")
    tracker = WorkspaceRunTracker(repo, first.id)

    with pytest.raises(ValueError, match="does not belong to workspace"):
        tracker.begin_core([foreign_product.id])

    assert repo.latest_run(foreign_product.id) is None
