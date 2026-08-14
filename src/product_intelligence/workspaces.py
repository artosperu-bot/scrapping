from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import sqlite3
from typing import Mapping
from uuid import uuid4


class Stage(str, Enum):
    IDENTITY = "IDENTITY"
    EVIDENCE = "EVIDENCE"
    PDFS = "PDFS"
    CANONICAL = "CANONICAL"
    EXCEL = "EXCEL"
    MULTIMEDIA = "MULTIMEDIA"
    PRICES = "PRICES"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    PAUSED = "PAUSED"


@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    excel_path: str | None
    template_profile_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class WorkspaceProduct:
    id: str
    workspace_id: str
    part_number: str
    brand: str | None
    model: str | None
    created_at: str


@dataclass(frozen=True)
class ProductRun:
    id: str
    product_id: str
    status: RunStatus
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StageState:
    run_id: str
    stage: Stage
    status: RunStatus
    updated_at: str
    error: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        self._conn.close()

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                excel_path TEXT,
                template_profile_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workspace_products (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                part_number TEXT NOT NULL,
                brand TEXT,
                model TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workspace_products_workspace
                ON workspace_products(workspace_id);
            CREATE TABLE IF NOT EXISTS product_runs (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES workspace_products(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_product_runs_product
                ON product_runs(product_id);
            CREATE TABLE IF NOT EXISTS stage_states (
                run_id TEXT NOT NULL REFERENCES product_runs(id) ON DELETE CASCADE,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error TEXT,
                PRIMARY KEY (run_id, stage)
            );
            """
        )
        self._conn.commit()

    def create_workspace(
        self,
        name: str,
        *,
        excel_path: str | None = None,
        template_profile_id: str | None = None,
    ) -> Workspace:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("workspace name is required")
        workspace_id = str(uuid4())
        stamp = _now()
        with self._conn:
            self._conn.execute(
                "INSERT INTO workspaces (id, name, excel_path, template_profile_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (workspace_id, clean_name, excel_path, template_profile_id, stamp, stamp),
            )
        return self.get_workspace(workspace_id)

    def get_workspace(self, workspace_id: str) -> Workspace:
        row = self._conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        if row is None:
            raise KeyError(workspace_id)
        return Workspace(**dict(row))

    def list_workspaces(self) -> list[Workspace]:
        rows = self._conn.execute("SELECT * FROM workspaces ORDER BY created_at, id").fetchall()
        return [Workspace(**dict(row)) for row in rows]

    def add_product(
        self,
        workspace_id: str,
        *,
        part_number: str,
        brand: str | None = None,
        model: str | None = None,
    ) -> WorkspaceProduct:
        self.get_workspace(workspace_id)
        clean_part_number = str(part_number or "").strip()
        if not clean_part_number:
            raise ValueError("part_number is required")
        product_id = str(uuid4())
        stamp = _now()
        with self._conn:
            self._conn.execute(
                "INSERT INTO workspace_products (id, workspace_id, part_number, brand, model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (product_id, workspace_id, clean_part_number, brand, model, stamp),
            )
        return self.find_product(workspace_id, clean_part_number)

    def find_product(self, workspace_id: str, part_number: str) -> WorkspaceProduct | None:
        row = self._conn.execute(
            "SELECT * FROM workspace_products WHERE workspace_id = ? AND part_number = ? ORDER BY created_at, id LIMIT 1",
            (workspace_id, str(part_number or "").strip()),
        ).fetchone()
        return WorkspaceProduct(**dict(row)) if row is not None else None

    def list_products(self, workspace_id: str) -> list[WorkspaceProduct]:
        rows = self._conn.execute(
            "SELECT * FROM workspace_products WHERE workspace_id = ? ORDER BY created_at, id",
            (workspace_id,),
        ).fetchall()
        return [WorkspaceProduct(**dict(row)) for row in rows]

    def create_run(self, product_id: str) -> ProductRun:
        product = self._conn.execute("SELECT id FROM workspace_products WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            raise KeyError(product_id)
        run_id = str(uuid4())
        stamp = _now()
        with self._conn:
            self._conn.execute(
                "INSERT INTO product_runs (id, product_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, product_id, RunStatus.PENDING.value, stamp, stamp),
            )
            self._conn.executemany(
                "INSERT INTO stage_states (run_id, stage, status, updated_at, error) VALUES (?, ?, ?, ?, NULL)",
                [(run_id, stage.value, RunStatus.PENDING.value, stamp) for stage in Stage],
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> ProductRun:
        row = self._conn.execute("SELECT * FROM product_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return ProductRun(
            id=row["id"],
            product_id=row["product_id"],
            status=RunStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def latest_run(self, product_id: str) -> ProductRun | None:
        row = self._conn.execute(
            "SELECT * FROM product_runs WHERE product_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (product_id,),
        ).fetchone()
        if row is None:
            return None
        return ProductRun(
            id=row["id"],
            product_id=row["product_id"],
            status=RunStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _aggregate_run_status(states: Mapping[Stage, StageState]) -> RunStatus:
        statuses = [state.status for state in states.values()]
        if any(status is RunStatus.ERROR for status in statuses):
            return RunStatus.ERROR
        if any(status is RunStatus.RUNNING for status in statuses):
            return RunStatus.RUNNING
        if statuses and all(status is RunStatus.COMPLETED for status in statuses):
            return RunStatus.COMPLETED
        if any(status is RunStatus.PAUSED for status in statuses):
            return RunStatus.PAUSED
        return RunStatus.PENDING

    def _refresh_run_status(self, run_id: str, stamp: str | None = None) -> None:
        stamp = stamp or _now()
        aggregate = self._aggregate_run_status(self.list_stage_states(run_id))
        self._conn.execute(
            "UPDATE product_runs SET status = ?, updated_at = ? WHERE id = ?",
            (aggregate.value, stamp, run_id),
        )

    def set_stage_status(
        self,
        run_id: str,
        stage: Stage,
        status: RunStatus,
        *,
        error: str | None = None,
    ) -> StageState:
        stamp = _now()
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE stage_states SET status = ?, updated_at = ?, error = ? WHERE run_id = ? AND stage = ?",
                (status.value, stamp, error, run_id, stage.value),
            )
            if cursor.rowcount != 1:
                raise KeyError((run_id, stage.value))
            self._refresh_run_status(run_id, stamp)
        return self.list_stage_states(run_id)[stage]

    def list_stage_states(self, run_id: str) -> Mapping[Stage, StageState]:
        rows = self._conn.execute(
            "SELECT * FROM stage_states WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        by_stage = {
            Stage(row["stage"]): StageState(
                run_id=row["run_id"],
                stage=Stage(row["stage"]),
                status=RunStatus(row["status"]),
                updated_at=row["updated_at"],
                error=row["error"],
            )
            for row in rows
        }
        return {stage: by_stage[stage] for stage in Stage if stage in by_stage}

    def recover_running_stages(self) -> int:
        stamp = _now()
        affected = [
            row["run_id"]
            for row in self._conn.execute(
                "SELECT DISTINCT run_id FROM stage_states WHERE status = ?",
                (RunStatus.RUNNING.value,),
            ).fetchall()
        ]
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE stage_states SET status = ?, updated_at = ?, error = NULL WHERE status = ?",
                (RunStatus.PENDING.value, stamp, RunStatus.RUNNING.value),
            )
            for run_id in affected:
                self._refresh_run_status(run_id, stamp)
        return int(cursor.rowcount)
