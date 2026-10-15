"""Slow strategic cycle with fixed report membership and one atomic state commit."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .context_builder import prose
from .ids import next_id
from .schemas import BrainOutput

STRATEGY_FILES = {
    "strategy_artifact": ("strategy/CURRENT_STRATEGY.md", False),
    "direction_tree_artifact": ("strategy/DIRECTION_TREE.md", False),
    "insight_log_appendix": ("strategy/INSIGHT_LOG.md", True),
    "decision_log_appendix": ("strategy/DECISION_LOG.md", True),
    "open_questions_artifact": ("strategy/OPEN_QUESTIONS.md", False),
}


class BrainRunner:
    def __init__(self, services: Any):
        self.s = services

    def validate(self, output: BrainOutput) -> None:
        existing = {r["public_id"] for r in self.s.db.query("SELECT public_id FROM insights")}
        updated = []
        for update in output.insight_updates:
            if update.insight_id not in existing:
                raise ValueError(f"Unknown insight update: {update.insight_id}")
            updated.append(update.insight_id)
        if len(set(updated)) != len(updated):
            raise ValueError("An insight may only be updated once per cycle")
        for proposal in output.branch_proposals:
            if (
                proposal.parent_insight_id is not None
                and proposal.parent_insight_id not in existing
            ):
                raise ValueError(f"Unknown parent insight: {proposal.parent_insight_id}")
            if proposal.new_insight_index is not None and proposal.new_insight_index >= len(
                output.new_insights
            ):
                raise ValueError("Branch new_insight_index is outside this cycle proposals")

    async def run(self, cycle_id: int, guard: Callable[..., None]) -> int:
        s = self.s
        cycle = s.db.one("SELECT * FROM brain_cycles WHERE id=?", (cycle_id,))
        if cycle["status"] == "COMPLETED":
            s.reconcile()
            return cycle_id
        guard()
        with s.db.transaction() as c:
            guard(c)
            c.execute("UPDATE brain_cycles SET status='RUNNING' WHERE id=?", (cycle_id,))
        metadata = {"project": s.db.project["slug"], "cycle": str(cycle_id)}
        context_path = f"raw/contexts/brain-{cycle_id}.json"
        if not s.paths.resolve(context_path).exists():
            s.paths.write_immutable(context_path, s.contexts.brain(cycle_id))
        context = s.paths.read(context_path)
        result = await s.gateway.run_structured(
            role="brain",
            action_key=f"brain:{cycle_id}",
            input_text=context,
            output_type=BrainOutput,
            metadata=metadata,
        )
        try:
            self.validate(result.output)
        except ValueError as exc:
            result = await s.gateway.run_structured(
                role="brain",
                action_key=f"brain:{cycle_id}:retry",
                input_text=json.dumps(
                    {"context": json.loads(context), "validation_feedback": str(exc)}
                ),
                output_type=BrainOutput,
                metadata=metadata,
            )
            self.validate(result.output)
        output = result.output
        staged = []
        for field, (destination, append_only) in STRATEGY_FILES.items():
            content = getattr(output, field).content
            if field == "strategy_artifact":
                content = prose(
                    {
                        "global_assessment": output.global_assessment,
                        "proof_vs_disproof_assessment": output.proof_vs_disproof_assessment,
                        "strategy": content,
                    }
                )
            artifact = await s.artifacts.persist(
                key=f"brain:{cycle_id}:{field}",
                kind=field,
                scope=str(cycle_id),
                raw_content=content,
                mode="aggressive",
                destination=destination,
                metadata=metadata,
                model_run_id=result.run_id,
                publish=False,
            )
            staged.append((artifact, destination, append_only))
        new = []
        for index, proposal in enumerate(output.new_insights):
            artifact = await s.artifacts.persist(
                key=f"brain:{cycle_id}:insight:{index}",
                kind="insight",
                scope=str(cycle_id),
                raw_content=prose(proposal.model_dump(exclude={"priority", "confidence"})),
                mode="aggressive",
                destination=f"strategy/cycles/C-{cycle_id:06}/insight-{index}.md",
                metadata=metadata,
                model_run_id=result.run_id,
                publish=False,
            )
            new.append((proposal, artifact))
        updates = []
        for update in output.insight_updates:
            artifact = await s.artifacts.persist(
                key=f"brain:{cycle_id}:update:{update.insight_id}",
                kind="insight_update",
                scope=str(cycle_id),
                raw_content=update.reason,
                mode="aggressive",
                destination=f"strategy/cycles/C-{cycle_id:06}/{update.insight_id}-update.md",
                metadata={**metadata, "insight": update.insight_id},
                model_run_id=result.run_id,
                publish=False,
            )
            updates.append((update, artifact))
        active = s.db.one(
            "SELECT COUNT(*) AS n FROM branches WHERE status IN ('QUEUED','RUNNING','WAITING_FOR_SOLVER','WAITING_FOR_MANAGER','FAILED')"
        )["n"]
        cap = max(
            0,
            min(
                s.config.limits.max_new_branches_per_brain_cycle,
                s.config.limits.max_active_branches - active,
            ),
        )
        branch_proposals = []
        for index, proposal in enumerate(output.branch_proposals[:cap]):
            artifact = await s.artifacts.persist(
                key=f"brain:{cycle_id}:branch:{index}",
                kind="branch_context",
                scope=str(cycle_id),
                raw_content=prose(
                    proposal.model_dump(
                        exclude={"parent_insight_id", "new_insight_index", "priority"}
                    )
                ),
                mode="prompt",
                destination=f"strategy/cycles/C-{cycle_id:06}/branch-{index}.md",
                metadata=metadata,
                model_run_id=result.run_id,
                publish=False,
            )
            branch_proposals.append((index, proposal, artifact))
        guard()
        with s.db.transaction() as c:
            guard(c)
            current = c.execute(
                "SELECT status FROM brain_cycles WHERE id=?", (cycle_id,)
            ).fetchone()
            if current["status"] == "COMPLETED":
                return cycle_id
            assigned = []
            for proposal, artifact in new:
                public_id = next_id(c, "insight")
                insight_id = c.execute(
                    "INSERT INTO insights(public_id,summary,status,confidence,created_cycle_id,updated_cycle_id,artifact_id) "
                    "VALUES(?,?,'ACTIVE',?,?,?,?)",
                    (
                        public_id,
                        s.artifacts.content(artifact["id"]),
                        proposal.confidence,
                        cycle_id,
                        cycle_id,
                        artifact["id"],
                    ),
                ).lastrowid
                assigned.append(insight_id)
                c.execute(
                    "INSERT INTO insight_events(insight_id,cycle_id,status,artifact_id) VALUES(?,?,'ACTIVE',?)",
                    (insight_id, cycle_id, artifact["id"]),
                )
            for update, artifact in updates:
                insight = c.execute(
                    "SELECT id FROM insights WHERE public_id=?", (update.insight_id,)
                ).fetchone()
                c.execute(
                    "UPDATE insights SET status=?,updated_cycle_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (update.new_status, cycle_id, insight["id"]),
                )
                c.execute(
                    "INSERT INTO insight_events(insight_id,cycle_id,status,artifact_id) VALUES(?,?,?,?)",
                    (insight["id"], cycle_id, update.new_status, artifact["id"]),
                )
            # Recheck under transaction: no other process may exceed active branch budget.
            current_active = c.execute(
                "SELECT COUNT(*) FROM branches WHERE status IN ('QUEUED','RUNNING','WAITING_FOR_SOLVER','WAITING_FOR_MANAGER','FAILED')"
            ).fetchone()[0]
            for index, proposal, artifact in branch_proposals[
                : max(0, s.config.limits.max_active_branches - current_active)
            ]:
                parent = (
                    assigned[proposal.new_insight_index]
                    if proposal.new_insight_index is not None
                    else c.execute(
                        "SELECT id FROM insights WHERE public_id=?", (proposal.parent_insight_id,)
                    ).fetchone()["id"]
                )
                public_id = next_id(c, "branch")
                priority = {"low": 0, "medium": 1, "high": 2}[proposal.priority]
                c.execute(
                    "INSERT INTO branches(public_id,parent_insight_id,status,priority,created_cycle_id,proposal_index,context_artifact_id) "
                    "VALUES(?,?,'QUEUED',?,?,?,?)",
                    (public_id, parent, priority, cycle_id, index, artifact["id"]),
                )
                c.execute(
                    "INSERT INTO jobs(job_type,scope_type,scope_id,max_attempts,priority) VALUES('RUN_BRANCH','branch',?,?,?)",
                    (public_id, s.config.limits.max_model_attempts, priority),
                )
            for artifact, destination, append_only in staged:
                c.execute(
                    "INSERT INTO cycle_artifacts(cycle_id,artifact_id,destination,append_only) VALUES(?,?,?,?)",
                    (cycle_id, artifact["id"], destination, int(append_only)),
                )
            c.execute(
                "UPDATE reports SET processed_cycle_id=? WHERE processed_cycle_id IS NULL AND id IN "
                "(SELECT report_id FROM cycle_reports WHERE cycle_id=?)",
                (cycle_id, cycle_id),
            )
            c.execute(
                "UPDATE brain_cycles SET status='COMPLETED',completed_at=CURRENT_TIMESTAMP,raw_output_path=?,edited_output_path=? WHERE id=?",
                (result.raw_path, staged[0][0]["edited_path"], cycle_id),
            )
        s.reconcile()
        return cycle_id
