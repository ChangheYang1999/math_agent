"""One bounded Manager/Solver loop. Every stage can be replayed from durable caches."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .context_builder import prose
from .ids import probe_id
from .models import is_legal_branch_transition
from .schemas import ProbeAssessment, ProbeFormulation, SolverOutput

ACTIONS = {
    "CONFIRM": "CONFIRMED",
    "REFUTE": "REFUTED",
    "PARTIAL": "PARTIALLY_SUPPORTED",
    "TOO_HARD": "TOO_HARD",
    "ABANDON": "ABANDONED",
}


class BranchRunner:
    def __init__(self, services: Any):
        self.s = services
        self.guard: Callable[..., None] | None = None

    def _execute(self, sql: str, params: tuple = ()) -> None:
        with self.s.db.transaction() as connection:
            if self.guard is not None:
                self.guard(connection)
            connection.execute(sql, params)

    def transition(self, public_id: str, target: str, *, recovery: bool = False) -> None:
        with self.s.db.transaction() as c:
            if self.guard is not None:
                self.guard(c)
            row = c.execute(
                "SELECT status FROM branches WHERE public_id=?", (public_id,)
            ).fetchone()
            old = row["status"]
            if old == target:
                return
            if not recovery and not is_legal_branch_transition(old, target):
                raise ValueError(f"Illegal branch transition {old} -> {target}")
            c.execute(
                "UPDATE branches SET status=?,updated_at=CURRENT_TIMESTAMP WHERE public_id=?",
                (target, public_id),
            )
            c.execute(
                "INSERT INTO state_events(entity_type,entity_id,old_status,new_status) VALUES(?,?,?,?)",
                ("branch", public_id, old, target),
            )

    async def run(self, public_id: str, guard: Callable[..., None]) -> int:
        self.guard = guard
        s = self.s
        branch = s.db.one("SELECT * FROM branches WHERE public_id=?", (public_id,))
        if not branch:
            raise ValueError("Unknown branch")
        if branch["final_report_id"]:
            return branch["final_report_id"]
        guard()
        self.transition(public_id, "RUNNING", recovery=True)
        key = f"branch:{public_id}"
        metadata = {"project": s.db.project["slug"], "branch": public_id}
        result = await s.gateway.run_structured(
            role="probe_manager",
            action_key=f"{key}:formulate",
            input_text=s.contexts.manager(branch["id"]),
            output_type=ProbeFormulation,
            metadata=metadata,
        )
        form = result.output
        status = "TOO_HARD"
        reason = ""
        for round_number in range(1, s.config.limits.max_probe_rounds + 1):
            guard()
            qid = probe_id(public_id, round_number)
            metadata = {**metadata, "probe": qid}
            with s.db.transaction() as c:
                guard(c)
                c.execute(
                    "INSERT INTO probes(branch_id,public_id,round_number,status) VALUES(?,?,?,'DRAFTED') ON CONFLICT(branch_id,round_number) DO NOTHING",
                    (branch["id"], qid, round_number),
                )
                c.execute(
                    "UPDATE branches SET probe_round=? WHERE id=?", (round_number, branch["id"])
                )
            probe = s.db.one("SELECT * FROM probes WHERE public_id=?", (qid,))
            base = f"branches/{public_id}/{qid}"
            data = form.model_dump()
            # Solver sees the precise local mathematics, not strategic preference.
            local = {
                k: data[k]
                for k in (
                    "mathematical_question",
                    "assumptions",
                    "forbidden_assumptions",
                    "proof_criterion",
                    "disproof_criterion",
                )
            }
            local["statement_notes"] = form.artifact.content
            statement = await s.artifacts.persist(
                key=f"{key}:problem:{round_number}",
                kind="probe",
                scope=qid,
                raw_content=prose(local),
                mode="prompt",
                destination=f"{base}/problem.md",
                metadata=metadata,
                model_run_id=result.run_id,
            )
            criteria = await s.artifacts.persist(
                key=f"{key}:criteria:{round_number}",
                kind="probe_criteria",
                scope=qid,
                raw_content=prose(
                    {
                        k: data[k]
                        for k in (
                            "implication_if_proved",
                            "implication_if_disproved",
                            "implication_if_inconclusive",
                            "relevance_to_parent_insight",
                        )
                    }
                ),
                mode="aggressive",
                destination=f"{base}/criteria.md",
                metadata=metadata,
                model_run_id=result.run_id,
            )
            guard()
            self._execute(
                "UPDATE probes SET statement_edited_path=? WHERE id=?",
                (statement["edited_path"], probe["id"]),
            )
            if probe["verdict"] is None:
                self._execute("UPDATE probes SET status='EDITED' WHERE id=?", (probe["id"],))
            self.transition(public_id, "WAITING_FOR_SOLVER")
            if probe["verdict"] is None:
                self._execute("UPDATE probes SET status='SOLVING' WHERE id=?", (probe["id"],))
            solved = await s.gateway.run_structured(
                role="solver",
                action_key=f"{key}:solve:{round_number}",
                input_text=s.contexts.solver(probe["id"]),
                output_type=SolverOutput,
                metadata=metadata,
            )
            guard()
            output = solved.output
            self._execute(
                "UPDATE probes SET verdict=?,status='SOLVED',solver_raw_path=? WHERE id=?",
                (output.verdict, solved.raw_path, probe["id"]),
            )
            report = await s.artifacts.persist(
                key=f"{key}:solver:{round_number}",
                kind="solver",
                scope=qid,
                raw_content=prose(output.model_dump(exclude={"verdict"})),
                mode="proof_safe",
                destination=f"{base}/solver_report.md",
                metadata={**metadata, "verdict": output.verdict},
                model_run_id=solved.run_id,
            )
            guard()
            self._execute(
                "UPDATE probes SET solver_raw_path=?,solver_edited_path=? WHERE id=?",
                (report["raw_path"], report["edited_path"], probe["id"]),
            )
            self.transition(public_id, "WAITING_FOR_MANAGER")
            assessed = await s.gateway.run_structured(
                role="probe_manager",
                action_key=f"{key}:assess:{round_number}",
                input_text=json.dumps(
                    {
                        "task": "Assess local result",
                        "local_context": s.contexts.manager(branch["id"]),
                        "strategic_criteria": s.artifacts.content(criteria["id"]),
                        "solver_verdict": output.verdict,
                        "solver_report": s.artifacts.content(report["id"]),
                        "editor_consistency_issues": json.loads(report["consistency_issues"]),
                        "round": round_number,
                        "max_rounds": s.config.limits.max_probe_rounds,
                    },
                    ensure_ascii=False,
                ),
                output_type=ProbeAssessment,
                metadata=metadata,
            )
            assessment = assessed.output
            if assessment.solver_verdict != output.verdict:
                raise ValueError("Manager changed the historical Solver verdict")
            interpretation = await s.artifacts.persist(
                key=f"{key}:assessment:{round_number}",
                kind="assessment",
                scope=qid,
                raw_content=prose(
                    assessment.model_dump(exclude={"action", "solver_verdict", "next_probe"})
                ),
                mode="aggressive",
                destination=f"{base}/assessment.md",
                metadata={**metadata, "action": assessment.action},
                model_run_id=assessed.run_id,
            )
            guard()
            self._execute(
                "UPDATE probes SET status='ASSESSED',assessment_action=?,manager_assessment_raw_path=?,manager_assessment_edited_path=?,completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (
                    assessment.action,
                    interpretation["raw_path"],
                    interpretation["edited_path"],
                    probe["id"],
                ),
            )
            if assessment.action == "REFORMULATE":
                if round_number == s.config.limits.max_probe_rounds:
                    status = "TOO_HARD"
                    reason = (
                        "Configured round limit reached; further local reformulation was rejected."
                    )
                    break
                form = assessment.next_probe
                result = assessed
                assert form is not None
            else:
                status = ACTIONS[assessment.action]
                break
        history = s.contexts.branch_history(branch["id"])
        parent = s.db.one(
            "SELECT public_id FROM insights WHERE id=?", (branch["parent_insight_id"],)
        )
        parts = [
            f"# Branch {public_id}\n\nParent insight: {parent['public_id']}\nFinal status: {status}\n\n{reason}"
        ]
        for item in history:
            detail = f"branches/{public_id}/{item['probe_id']}"
            parts.append(
                f"## {item['probe_id']}\n\nSolver verdict: {item['verdict']}\nManager action: {item['action']}"
            )
            for field, title, filename in (
                ("statement_edited_path", "Probe", "problem.md"),
                ("solver_edited_path", "Solver result", "solver_report.md"),
                ("manager_assessment_edited_path", "Local interpretation", "assessment.md"),
            ):
                if field in item:
                    parts.append(f"### {title}\n\nSource: {detail}/{filename}\n\n{item[field]}")
        raw = "\n\n".join(parts)
        final = await s.artifacts.persist(
            key=f"{key}:final",
            kind="branch_final",
            scope=public_id,
            raw_content=raw,
            mode="proof_safe",
            destination=f"branches/{public_id}/FINAL_REPORT.md",
            metadata=metadata,
        )
        guard()
        report_id = s.inbox.finalize_branch(branch["id"], status, final, guard=guard)
        report_row = s.db.one("SELECT * FROM reports WHERE id=?", (report_id,))
        s.paths.atomic_write(
            f"reports/inbox/{report_row['public_id']}.md", s.artifacts.content(final["id"])
        )
        return report_id
