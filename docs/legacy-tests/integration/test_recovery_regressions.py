import asyncio
import time

import pytest
from fixtures.scripted import ScriptGateway

from math_research_agent.artifacts import ArtifactService, EditorFailure
from math_research_agent.config import Config
from math_research_agent.db import Database
from math_research_agent.model_gateway import FakeModelGateway
from math_research_agent.orchestrator import Orchestrator
from math_research_agent.paths import Paths


async def test_rejected_cached_editor_can_be_retried(tmp_path):
    db = Database.initialize(tmp_path, "test", "Test")
    paths = Paths(tmp_path)
    config = Config(runtime={"retry_base_seconds": 0})
    gateway = FakeModelGateway(
        db,
        paths,
        config,
        script={
            "editor": [
                {"edited_content": "Changed to I-000002", "consistency_issues": []},
                {"edited_content": "Keep I-000001", "consistency_issues": []},
            ]
        },
    )
    artifacts = ArtifactService(db, paths, gateway)
    args = dict(
        key="one",
        kind="insight",
        scope="I-000001",
        raw_content="Keep I-000001",
        mode="aggressive",
        destination="insight.md",
    )
    with pytest.raises(EditorFailure):
        await artifacts.persist(**args)
    record = await artifacts.persist(**args)
    assert paths.read(record["edited_path"]) == "Keep I-000001"
    assert len(db.query("SELECT * FROM model_runs")) == 2


async def test_stale_exception_does_not_mark_replacement_branch_failed(tmp_path):
    db = Database.initialize(tmp_path, "test", "Test")
    gw = ScriptGateway()
    app = Orchestrator(db, Paths(tmp_path), Config(), gw)
    i = db.execute(
        "INSERT INTO insights(public_id,summary,status) VALUES('I-000001','human','ACTIVE')"
    )
    db.execute(
        "INSERT INTO branches(public_id,parent_insight_id,status) VALUES('B-000001',?,'QUEUED')",
        (i,),
    )
    job = app.jobs.enqueue("RUN_BRANCH", "branch", "B-000001")
    started = asyncio.Event()
    release = asyncio.Event()

    async def pending(**kwargs):
        started.set()
        await release.wait()
        raise RuntimeError("old request failed")

    gw.run_structured = pending
    old = asyncio.create_task(app.execute_job(job))
    await started.wait()
    db.execute("UPDATE jobs SET lease_expires_at=? WHERE id=?", (time.time() - 1, job))
    app.jobs.recover()
    token = app.jobs.claim(job)
    release.set()
    with pytest.raises(RuntimeError):
        await old
    assert db.one("SELECT lease_owner FROM jobs WHERE id=?", (job,))["lease_owner"] == token
    assert db.one("SELECT status FROM branches")["status"] == "RUNNING"


async def test_lost_lease_cannot_publish_editor_result(tmp_path):
    from types import SimpleNamespace

    from math_research_agent.execution import execution_scope

    db = Database.initialize(tmp_path, "test", "Test")
    paths = Paths(tmp_path)
    owned = True

    def guard(connection=None):
        if not owned:
            raise RuntimeError("Job lease lost")

    class LosingEditor:
        async def run_structured(self, **kw):
            nonlocal owned
            owned = False
            return SimpleNamespace(
                output=kw["output_type"](edited_content="Edited proof", consistency_issues=[]),
                run_id="editor",
            )

    artifacts = ArtifactService(db, paths, LosingEditor())
    with execution_scope(guard, {"job": "1"}):
        with pytest.raises(RuntimeError, match="lease"):
            await artifacts.persist(
                key="proof",
                kind="solver",
                scope="Q-000001.1",
                raw_content="Original proof",
                mode="proof_safe",
                destination="solver.md",
            )
    assert not paths.resolve("solver.md").exists()
    assert db.one("SELECT status FROM artifacts")["status"] == "EDITING"


async def test_standalone_edit_job_repairs_stage_without_publishing_uncommitted_strategy(tmp_path):

    db = Database.initialize(tmp_path, "test", "Test")
    paths = Paths(tmp_path)
    gw = ScriptGateway({"editor": [RuntimeError("offline")]})
    app = Orchestrator(db, paths, Config(), gw)
    with pytest.raises(EditorFailure):
        await app.artifacts.persist(
            key="cycle:1",
            kind="strategy",
            scope="1",
            raw_content="A strategic proposal",
            mode="aggressive",
            destination="strategy/CURRENT_STRATEGY.md",
            publish=False,
        )
    artifact = db.one("SELECT * FROM artifacts")
    job = app.jobs.enqueue("EDIT_ARTIFACT", "artifact", artifact["id"])
    await app.execute_job(job)
    assert db.one("SELECT status FROM artifacts")["status"] == "EDITED"
    assert db.one("SELECT status FROM jobs WHERE id=?", (job,))["status"] == "COMPLETED"
    assert not paths.resolve("strategy/CURRENT_STRATEGY.md").exists()
