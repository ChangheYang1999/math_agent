"""Human-triggered workflow facade. Agents never own orchestration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .artifacts import ArtifactService
from .branches import BranchRunner
from .config import Config
from .context_builder import ContextBuilder
from .db import Database
from .execution import execution_scope
from .inbox import Inbox
from .jobs import JobStore, JobUnavailableError
from .paths import Paths, project_root
from .scheduler import run_workers


class Orchestrator:
    def __init__(self, db: Database, paths: Paths, config: Config, gateway: Any):
        self.db, self.paths, self.config, self.gateway = db, paths, config, gateway
        self.artifacts = ArtifactService(db, paths, gateway, fail_closed=config.editor.fail_closed)
        self.contexts = ContextBuilder(db, paths, self.artifacts)
        self.jobs = JobStore(db, config.runtime.lease_seconds, config.limits.max_model_attempts)
        self.inbox = Inbox(db)
        self.recovered_jobs = self.jobs.recover()

    @staticmethod
    def initialize(projects_root: Path, slug: str, title: str) -> Path:
        root = project_root(projects_root, slug)
        paths = Paths(root)
        Database.initialize(root, slug, title)
        for folder in (
            "problem",
            "literature/papers",
            "reports/inbox",
            "reports/processed",
            "strategy",
            "branches",
            "raw/background",
            "raw/brain",
            "raw/branches",
            "raw/editor",
        ):
            paths.resolve(folder).mkdir(parents=True, exist_ok=True)
        paths.atomic_write("project.yaml", "# Project-specific configuration overrides\n{}\n")
        return root

    def set_problem(self, content: str) -> None:
        if not content.strip():
            raise ValueError("Problem cannot be empty")
        if self.db.one("SELECT id FROM jobs WHERE status IN ('RUNNING','QUEUED')"):
            raise ValueError("Finish or recover active jobs before changing the problem")
        if self.db.one("SELECT id FROM brain_cycles") or self.db.one(
            "SELECT id FROM jobs WHERE job_type='BACKGROUND'"
        ):
            raise ValueError("Research has started; create a new project for a different problem")
        self.paths.atomic_write("problem/original.md", content)

    async def workers(self, max_concurrent: int | None = None) -> list[dict]:
        return await run_workers(self, max_concurrent)

    async def run_branch(self, public_id: str) -> Any:
        if not self.db.one("SELECT id FROM branches WHERE public_id=?", (public_id,)):
            raise ValueError("Unknown branch")
        job = self.jobs.enqueue("RUN_BRANCH", "branch", public_id)
        return await self.execute_job(
            job, max_concurrent=self.config.limits.max_concurrent_branches
        )

    async def execute_job(self, job_id: int, max_concurrent: int | None = None) -> Any:
        row = self.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not row:
            raise ValueError("Unknown job")
        token = self.jobs.claim(job_id, max_concurrent=max_concurrent)
        if not token:
            current = self.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
            if current and current["status"] == "COMPLETED":
                if current["job_type"] == "RUN_BRANCH":
                    branch = self.db.one(
                        "SELECT final_report_id FROM branches WHERE public_id=?",
                        (current["scope_id"],),
                    )
                    return branch["final_report_id"]
                return current["id"]
            state = current["status"] if current else "missing"
            instruction = (
                "use retry for this failed job"
                if state == "FAILED"
                else "check status and try again when capacity is available"
            )
            raise JobUnavailableError(f"Job {job_id} did not run ({state}); {instruction}")

        def guard(connection=None):
            self.jobs.assert_owner(job_id, token, connection=connection)

        try:
            with execution_scope(guard, {"job": str(job_id), "project": self.db.project["slug"]}):
                async with self.jobs.heartbeat(job_id, token):
                    if row["job_type"] == "RUN_BRANCH":
                        result = await BranchRunner(self).run(row["scope_id"], guard)
                    elif row["job_type"] == "BRAIN":
                        from .brain import BrainRunner

                        result = await BrainRunner(self).run(int(row["scope_id"]), guard)
                    elif row["job_type"] == "BACKGROUND":
                        from .background import BackgroundRunner

                        result = await BackgroundRunner(self).run(job_id, guard)
                    elif row["job_type"] == "EDIT_ARTIFACT":
                        import json

                        artifact = self.db.one(
                            "SELECT * FROM artifacts WHERE id=?", (row["scope_id"],)
                        )
                        if artifact is None:
                            raise ValueError("Unknown artifact")
                        result = await self.artifacts.persist(
                            key=artifact["logical_key"],
                            kind=artifact["kind"],
                            scope=artifact["scope_id"],
                            raw_content=self.paths.read(artifact["raw_path"]),
                            mode=artifact["editor_mode"],
                            destination=artifact["destination"],
                            metadata=json.loads(artifact["metadata_json"]),
                            model_run_id=artifact["model_run_id"],
                            publish=False,
                        )
                    else:
                        raise ValueError("Unknown job type")
                    guard()
                    self.jobs.complete(job_id, token)
                    return result
        except BaseException as exc:
            # A stale owner must not mark a replacement worker's scope failed.
            with self.db.transaction() as c:
                failed = self.jobs.fail(job_id, token, exc, connection=c)
                if failed and row["job_type"] == "RUN_BRANCH":
                    c.execute(
                        "UPDATE branches SET status='FAILED',updated_at=CURRENT_TIMESTAMP "
                        "WHERE public_id=? AND final_report_id IS NULL",
                        (row["scope_id"],),
                    )
                elif failed and row["job_type"] == "BRAIN":
                    c.execute(
                        "UPDATE brain_cycles SET status='FAILED' WHERE id=? AND status!='COMPLETED'",
                        (row["scope_id"],),
                    )
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise

    async def retry(self, job_id: int) -> Any:
        self.jobs.retry(job_id)
        row = self.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        return await self.execute_job(
            job_id,
            max_concurrent=self.config.limits.max_concurrent_branches
            if row["job_type"] == "RUN_BRANCH"
            else None,
        )

    async def brain(self) -> Any:
        if not self.paths.resolve("problem/specification.md").is_file():
            raise ValueError("Run background before the first Brain cycle")
        if self.db.one("SELECT id FROM jobs WHERE job_type='BACKGROUND' AND status!='COMPLETED'"):
            raise ValueError("Finish or retry background research before running Brain")
        active = self.db.one(
            "SELECT * FROM jobs WHERE job_type='BRAIN' AND status!='COMPLETED' ORDER BY id DESC LIMIT 1"
        )
        if active:
            if active["status"] == "QUEUED":
                return await self.execute_job(active["id"])
            raise ValueError("A Brain job is already active or failed; use status and retry")
        self.reconcile()
        cycle = self.inbox.snapshot(self.config.limits.max_model_attempts)
        job = self.db.one(
            "SELECT id FROM jobs WHERE job_type='BRAIN' AND scope_id=?", (str(cycle),)
        )
        return await self.execute_job(job["id"])

    def reconcile(self) -> None:
        """Repair canonical views from committed immutable versions after interruption."""
        grouped = {}
        rows = self.db.query(
            "SELECT ca.*,a.edited_path,a.status,a.content_sha256_edited FROM cycle_artifacts ca "
            "JOIN brain_cycles bc ON bc.id=ca.cycle_id JOIN artifacts a ON a.id=ca.artifact_id "
            "WHERE bc.status='COMPLETED' ORDER BY bc.cycle_number"
        )
        for row in rows:
            content = self.artifacts.content(row["artifact_id"])
            if row["append_only"]:
                grouped.setdefault(row["destination"], []).append(
                    f"## Cycle {row['cycle_id']}\n\n{content}"
                )
            else:
                grouped[row["destination"]] = [content]
        events = self.db.query(
            "SELECT ie.*,i.public_id FROM insight_events ie JOIN insights i ON i.id=ie.insight_id ORDER BY ie.id"
        )
        if events:
            grouped.setdefault("strategy/INSIGHT_LOG.md", []).extend(
                f"## {row['public_id']} — {row['status']} (cycle {row['cycle_id']})\n\n{self.artifacts.content(row['artifact_id'])}"
                for row in events
            )
        for destination, parts in grouped.items():
            self.paths.atomic_write(destination, "\n\n".join(parts))
        for row in self.db.query("SELECT * FROM branches WHERE context_artifact_id IS NOT NULL"):
            self.paths.atomic_write(
                f"branches/{row['public_id']}/BRANCH_CONTEXT.md",
                self.artifacts.content(row["context_artifact_id"]),
            )
        for report in self.db.query("SELECT * FROM reports"):
            folder = "processed" if report["processed_cycle_id"] is not None else "inbox"
            content = self.paths.read(report["edited_path"])
            self.paths.atomic_write(f"reports/{folder}/{report['public_id']}.md", content)
            if folder == "processed":
                stale = self.paths.resolve(f"reports/inbox/{report['public_id']}.md")
                if (
                    stale.exists()
                    and str(stale.relative_to(self.paths.root)) != report["edited_path"]
                ):
                    stale.unlink()

    async def background(self) -> Any:
        from uuid import uuid4

        if not self.paths.resolve("problem/original.md").is_file():
            raise ValueError("Set the original problem before running background")
        with self.db.transaction() as c:
            if c.execute(
                "SELECT id FROM jobs WHERE job_type='BRAIN' AND status!='COMPLETED'"
            ).fetchone():
                raise ValueError("Finish the active Brain job before updating background")
            active = c.execute(
                "SELECT * FROM jobs WHERE job_type='BACKGROUND' AND status!='COMPLETED'"
            ).fetchone()
            if active:
                if active["status"] != "QUEUED":
                    raise ValueError(
                        "Background job already active or failed; use status and retry"
                    )
                job = active["id"]
            else:
                job = c.execute(
                    "INSERT INTO jobs(job_type,scope_type,scope_id,max_attempts) VALUES('BACKGROUND','project',?,?)",
                    (uuid4().hex, self.config.limits.max_model_attempts),
                ).lastrowid
        return await self.execute_job(job)

    def status(self) -> dict:
        import json

        project = self.db.project
        cycle = self.db.one("SELECT * FROM brain_cycles ORDER BY cycle_number DESC LIMIT 1")
        return {
            "project": project["slug"],
            "title": project["title"],
            "root": str(self.paths.root),
            "brain_cycle": cycle,
            "last_processed_report": self.db.one(
                "SELECT MAX(id) AS id FROM reports WHERE processed_cycle_id IS NOT NULL"
            )["id"],
            "insights": self.db.query("SELECT public_id,status,summary FROM insights ORDER BY id"),
            "branches": self.db.query(
                "SELECT public_id,status,probe_round,final_report_id FROM branches ORDER BY id"
            ),
            "inbox_count": self.db.one(
                "SELECT COUNT(*) AS n FROM reports WHERE processed_cycle_id IS NULL"
            )["n"],
            "jobs": self.db.query(
                "SELECT id,job_type,scope_id,status,attempts,max_attempts,error FROM jobs ORDER BY id"
            ),
            "usage": self.db.one(
                "SELECT COUNT(*) AS model_runs,SUM(input_tokens) AS input_tokens,SUM(output_tokens) AS output_tokens,"
                "SUM(total_tokens) AS total_tokens,SUM(estimated_cost_usd) AS estimated_cost_usd,"
                "SUM(reserved_cost_usd) AS reserved_cost_usd FROM model_runs"
            ),
            "editor_warnings": [
                {"artifact_id": r["id"], "issues": json.loads(r["consistency_issues"])}
                for r in self.db.query(
                    "SELECT id,consistency_issues FROM artifacts WHERE consistency_issues!='[]'"
                )
            ],
            "downloads": self.db.query(
                "SELECT reference_key,pdf_path,download_error FROM literature"
            ),
        }

    def inspect(self, kind: str, public_id: str) -> dict:
        tables = {
            "insight": "insights",
            "branch": "branches",
            "probe": "probes",
            "report": "reports",
        }
        if kind not in tables:
            raise ValueError("Unknown inspection kind")
        row = self.db.one(f"SELECT * FROM {tables[kind]} WHERE public_id=?", (public_id,))
        if row is None:
            raise ValueError(f"Unknown {kind}")
        sections = []
        raw_paths = []
        if kind == "insight":
            sections.append(row["summary"])
            artifacts = self.db.query(
                "SELECT a.* FROM artifacts a JOIN insight_events e ON e.artifact_id=a.id WHERE e.insight_id=? ORDER BY e.id",
                (row["id"],),
            )
        elif kind == "branch":
            artifacts = self.db.query(
                "SELECT * FROM artifacts WHERE scope_id=? OR scope_id IN "
                "(SELECT public_id FROM probes WHERE branch_id=?) ORDER BY created_at",
                (public_id, row["id"]),
            )
        elif kind == "probe":
            artifacts = self.db.query(
                "SELECT * FROM artifacts WHERE scope_id=? ORDER BY created_at", (public_id,)
            )
        else:
            artifacts = []
            sections.append(self.paths.read(row["edited_path"]))
            raw_paths.append(row["raw_path"])
        for artifact in artifacts:
            raw_paths.append(artifact["raw_path"])
            if artifact["edited_path"]:
                sections.append(self.artifacts.content(artifact["id"]))
        return {
            **row,
            "content": "\n\n".join(sections),
            "raw_paths": raw_paths,
            "artifacts": artifacts,
        }

    def add_correction(self, content: str, insight_public_id: str | None = None) -> str:
        from uuid import uuid4

        from .ids import next_id

        if not content.strip():
            raise ValueError("Correction cannot be empty")
        insight = None
        if insight_public_id:
            insight = self.db.one("SELECT id FROM insights WHERE public_id=?", (insight_public_id,))
            if insight is None:
                raise ValueError("Unknown insight")
        path = f"reports/corrections/{uuid4().hex}.md"
        self.paths.write_immutable(path, content)
        with self.db.transaction() as c:
            public_id = next_id(c, "report")
            c.execute(
                "INSERT INTO reports(public_id,insight_id,kind,raw_path,edited_path) VALUES(?,?,'HUMAN_CORRECTION',?,?)",
                (public_id, insight["id"] if insight else None, path, path),
            )
        self.reconcile()
        return public_id
