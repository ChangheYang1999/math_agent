"""Explicit role-specific views; no agent walks the project tree."""

from __future__ import annotations

import json

from .artifacts import ArtifactService
from .db import Database
from .paths import Paths


def prose(data: dict) -> str:
    """Render prose fields without interpreting their mathematical or workflow meaning."""
    sections = []
    for key, value in data.items():
        if value is None or value == []:
            continue
        if isinstance(value, dict):
            text = prose(value)
        elif isinstance(value, list):
            text = "\n".join(f"- {item}" for item in value)
        else:
            text = str(value)
        sections.append(f"## {key.replace('_', ' ')}\n{text}")
    return "\n\n".join(sections)


class ContextBuilder:
    def __init__(self, db: Database, paths: Paths, artifacts: ArtifactService):
        self.db, self.paths, self.artifacts = db, paths, artifacts

    def optional(self, path: str) -> str:
        return self.paths.read(path) if self.paths.resolve(path).is_file() else ""

    def brain(self, cycle_id: int) -> str:
        cycle = self.db.one("SELECT * FROM brain_cycles WHERE id=?", (cycle_id,))
        reports = self.db.query(
            "SELECT r.* FROM reports r JOIN cycle_reports cr ON cr.report_id=r.id "
            "WHERE cr.cycle_id=? ORDER BY r.id",
            (cycle_id,),
        )
        return json.dumps(
            {
                "cycle": cycle,
                "problem": self.optional("problem/specification.md"),
                "literature": self.optional("literature/AGENT_CONTEXT.md"),
                "strategy": self.optional("strategy/CURRENT_STRATEGY.md"),
                "insights": self.db.query(
                    "SELECT public_id,summary,status,confidence FROM insights WHERE status NOT IN ('ARCHIVED','SUPERSEDED')"
                ),
                "active_branches": self.db.query(
                    "SELECT public_id,parent_insight_id,status,probe_round FROM branches WHERE status IN ('QUEUED','RUNNING','WAITING_FOR_SOLVER','WAITING_FOR_MANAGER')"
                ),
                "reports": [
                    {
                        "report_id": r["public_id"],
                        "branch_id": r["branch_id"],
                        "content": self.paths.read(r["edited_path"]),
                    }
                    for r in reports
                ],
            },
            ensure_ascii=False,
        )

    def manager(self, branch_id: int) -> str:
        branch = self.db.one("SELECT * FROM branches WHERE id=?", (branch_id,))
        assert branch
        insight = self.db.one(
            "SELECT public_id,summary,status FROM insights WHERE id=?",
            (branch["parent_insight_id"],),
        )
        return json.dumps(
            {
                "parent_insight": insight,
                "local_objective": self.artifacts.content(branch["context_artifact_id"])
                if branch["context_artifact_id"]
                else "",
                "definitions": self.optional("problem/specification.md"),
                "literature": self.optional("literature/AGENT_CONTEXT.md"),
                "history": self.branch_history(branch_id),
            },
            ensure_ascii=False,
        )

    def branch_history(self, branch_id: int) -> list[dict]:
        result = []
        for probe in self.db.query(
            "SELECT * FROM probes WHERE branch_id=? ORDER BY round_number", (branch_id,)
        ):
            item = {
                "probe_id": probe["public_id"],
                "verdict": probe["verdict"],
                "action": probe["assessment_action"],
            }
            for field in (
                "statement_edited_path",
                "solver_edited_path",
                "manager_assessment_edited_path",
            ):
                if probe[field]:
                    item[field] = self.paths.read(probe[field])
            result.append(item)
        return result

    def solver(self, probe_id: int) -> str:
        probe = self.db.one(
            "SELECT public_id,statement_edited_path FROM probes WHERE id=?", (probe_id,)
        )
        if not probe or not probe["statement_edited_path"]:
            raise ValueError("Solver requires an edited probe")
        return json.dumps(
            {
                "probe_id": probe["public_id"],
                "problem": self.paths.read(probe["statement_edited_path"]),
            },
            ensure_ascii=False,
        )
