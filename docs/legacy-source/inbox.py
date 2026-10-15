"""Final report publication and exact, durable Brain snapshot membership."""

from __future__ import annotations

from collections.abc import Callable

from .db import Database
from .ids import next_id


class Inbox:
    def __init__(self, db: Database):
        self.db = db

    def snapshot(self, max_attempts: int = 3) -> int:
        with self.db.transaction() as c:
            if c.execute(
                "SELECT id FROM jobs WHERE job_type='BACKGROUND' AND status!='COMPLETED'"
            ).fetchone():
                raise ValueError("Finish the active background job before starting Brain")
            if c.execute(
                "SELECT 1 FROM brain_cycles WHERE status IN ('PENDING','RUNNING')"
            ).fetchone():
                raise ValueError("A Brain cycle is already active; resume its job")
            number = c.execute(
                "SELECT COALESCE(MAX(cycle_number),0)+1 FROM brain_cycles"
            ).fetchone()[0]
            previous = c.execute(
                "SELECT COALESCE(MAX(snapshot_report_id),0) FROM brain_cycles WHERE status=?",
                ("COMPLETED",),
            ).fetchone()[0]
            high = c.execute(
                "SELECT COALESCE(MAX(id),0) FROM reports WHERE status='FINALIZED'"
            ).fetchone()[0]
            cycle = c.execute(
                "INSERT INTO brain_cycles(cycle_number,status,snapshot_report_id,previous_checkpoint_report_id) VALUES(?,'PENDING',?,?)",
                (number, high, previous),
            ).lastrowid
            c.execute(
                "INSERT INTO cycle_reports(cycle_id,report_id) SELECT ?,id FROM reports WHERE status='FINALIZED' AND processed_cycle_id IS NULL AND id<=?",
                (cycle, high),
            )
            c.execute(
                "INSERT INTO jobs(job_type,scope_type,scope_id,max_attempts) VALUES('BRAIN','cycle',?,?)",
                (str(cycle), max_attempts),
            )
            return cycle

    def finalize_branch(
        self, branch_id: int, status: str, artifact: dict, guard: Callable[..., None] | None = None
    ) -> int:
        with self.db.transaction() as c:
            if guard is not None:
                guard(c)
            branch = c.execute("SELECT * FROM branches WHERE id=?", (branch_id,)).fetchone()
            if branch["final_report_id"]:
                return branch["final_report_id"]
            report = c.execute(
                "INSERT INTO reports(public_id,branch_id,insight_id,kind,raw_path,edited_path) VALUES(?,?,?,?,?,?)",
                (
                    next_id(c, "report"),
                    branch_id,
                    branch["parent_insight_id"],
                    "BRANCH_FINAL",
                    artifact["raw_path"],
                    artifact["edited_path"],
                ),
            ).lastrowid
            c.execute(
                "UPDATE branches SET status=?,final_report_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, report, branch_id),
            )
            c.execute(
                "INSERT INTO state_events(entity_type,entity_id,old_status,new_status) VALUES(?,?,?,?)",
                ("branch", branch["public_id"], branch["status"], status),
            )
            return report
