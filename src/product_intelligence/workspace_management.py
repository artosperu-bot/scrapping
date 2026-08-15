from __future__ import annotations

from .workspaces import WorkspaceRepository


def delete_workspace_record(repo: WorkspaceRepository, workspace_id: str) -> None:
    """Delete only persistent workspace metadata; physical files are managed separately."""
    repo.get_workspace(workspace_id)
    with repo._conn:  # repository owns this connection; FK cascades remove products/runs/stages.
        repo._conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
