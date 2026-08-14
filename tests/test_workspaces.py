from product_intelligence.workspaces import RunStatus, Stage, WorkspaceRepository


def test_workspace_persists_across_repository_reopen(tmp_path):
    db = tmp_path / "workspaces.db"
    repo = WorkspaceRepository(db)
    workspace = repo.create_workspace("Falabella Celulares Agosto", excel_path="catalogo.xlsx", template_profile_id="falabella")
    product = repo.add_product(workspace.id, part_number="ARMOR-22-256G", brand="Ulefone", model="Armor 22")
    run = repo.create_run(product.id)
    repo.set_stage_status(run.id, Stage.IDENTITY, RunStatus.COMPLETED)
    repo.close()

    reopened = WorkspaceRepository(db)
    loaded = reopened.get_workspace(workspace.id)
    products = reopened.list_products(workspace.id)
    stages = reopened.list_stage_states(run.id)

    assert loaded.name == "Falabella Celulares Agosto"
    assert loaded.excel_path == "catalogo.xlsx"
    assert loaded.template_profile_id == "falabella"
    assert [p.id for p in products] == [product.id]
    assert stages[Stage.IDENTITY].status is RunStatus.COMPLETED


def test_products_are_isolated_by_workspace(tmp_path):
    repo = WorkspaceRepository(tmp_path / "workspaces.db")
    first = repo.create_workspace("Falabella")
    second = repo.create_workspace("Ripley")
    p1 = repo.add_product(first.id, part_number="AAA")
    p2 = repo.add_product(second.id, part_number="BBB")

    assert [p.id for p in repo.list_products(first.id)] == [p1.id]
    assert [p.id for p in repo.list_products(second.id)] == [p2.id]


def test_new_run_initializes_all_pipeline_stages_pending(tmp_path):
    repo = WorkspaceRepository(tmp_path / "workspaces.db")
    workspace = repo.create_workspace("Test")
    product = repo.add_product(workspace.id, part_number="PN-1")
    run = repo.create_run(product.id)

    states = repo.list_stage_states(run.id)

    assert list(states) == list(Stage)
    assert all(state.status is RunStatus.PENDING for state in states.values())


def test_latest_run_and_product_lookup_support_incremental_resume(tmp_path):
    repo = WorkspaceRepository(tmp_path / "workspaces.db")
    workspace = repo.create_workspace("Test")
    product = repo.add_product(workspace.id, part_number="PN-1", brand="Brand")
    first = repo.create_run(product.id)
    second = repo.create_run(product.id)

    assert repo.find_product(workspace.id, "PN-1") == product
    assert repo.latest_run(product.id).id == second.id
    assert first.id != second.id


def test_run_status_is_derived_from_all_stage_states(tmp_path):
    repo = WorkspaceRepository(tmp_path / "workspaces.db")
    workspace = repo.create_workspace("Test")
    product = repo.add_product(workspace.id, part_number="PN-1")
    run = repo.create_run(product.id)

    repo.set_stage_status(run.id, Stage.IDENTITY, RunStatus.COMPLETED)
    assert repo.get_run(run.id).status is RunStatus.PENDING

    repo.set_stage_status(run.id, Stage.EVIDENCE, RunStatus.RUNNING)
    assert repo.get_run(run.id).status is RunStatus.RUNNING

    repo.set_stage_status(run.id, Stage.EVIDENCE, RunStatus.ERROR, error="boom")
    assert repo.get_run(run.id).status is RunStatus.ERROR
