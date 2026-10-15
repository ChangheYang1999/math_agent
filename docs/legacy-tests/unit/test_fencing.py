import asyncio
import time

import pytest
from fixtures.scripted import ScriptGateway, assessment, brain_output, formulation, solver

from math_research_agent.brain import BrainRunner
from math_research_agent.branches import BranchRunner
from math_research_agent.config import Config
from math_research_agent.db import Database
from math_research_agent.orchestrator import Orchestrator
from math_research_agent.paths import Paths


def app_at(tmp_path):
    db = Database.initialize(tmp_path, "test", "Test")
    return Orchestrator(db, Paths(tmp_path), Config(), ScriptGateway())


def seed_branch(app):
    insight = app.db.execute(
        "INSERT INTO insights(public_id,summary,status) VALUES('I-000001','Test','ACTIVE')"
    )
    branch = app.db.execute(
        "INSERT INTO branches(public_id,parent_insight_id,status) VALUES('B-000001',?,'QUEUED')",
        (insight,),
    )
    job = app.jobs.enqueue("RUN_BRANCH", "branch", "B-000001")
    return branch, job, app.jobs.claim(job)


def take_over(app, job):
    app.db.execute("UPDATE jobs SET lease_expires_at=? WHERE id=?", (time.time() - 1, job))
    app.jobs.recover()
    owner = app.jobs.claim(job)
    assert owner
    return owner


def test_owner_and_failure_use_callers_transaction(tmp_path):
    app = app_at(tmp_path)
    _, job, owner = seed_branch(app)
    with app.db.transaction() as connection:
        connection.execute("UPDATE jobs SET lease_owner=? WHERE id=?", ("replacement", job))
        # A separate connection sees the original token until this transaction commits.
        with pytest.raises(RuntimeError, match="lease"):
            app.jobs.assert_owner(job, owner, connection)
        assert app.jobs.fail(job, owner, RuntimeError(), connection) is False
        assert app.jobs.fail(job, "replacement", RuntimeError(), connection) is True
    assert app.db.one("SELECT status FROM jobs WHERE id=?", (job,))["status"] == "FAILED"


def test_complete_checks_ownership_in_its_write_transaction(tmp_path, monkeypatch):
    app = app_at(tmp_path)
    _, job, owner = seed_branch(app)
    original = app.jobs.assert_owner
    observed = []

    def check(job_id, token, connection=None):
        assert connection is not None and connection.in_transaction
        observed.append(connection)
        original(job_id, token, connection)

    monkeypatch.setattr(app.jobs, "assert_owner", check)
    app.jobs.complete(job, owner)
    assert observed
    assert app.db.one("SELECT status FROM jobs WHERE id=?", (job,))["status"] == "COMPLETED"


async def test_heartbeat_checks_and_renews_in_one_transaction(tmp_path, monkeypatch):
    app = app_at(tmp_path)
    app.jobs.lease_seconds = 0.09
    _, job, owner = seed_branch(app)
    original = app.jobs.assert_owner
    observed = []

    def check(job_id, token, connection=None):
        assert connection is not None and connection.in_transaction
        observed.append(connection)
        original(job_id, token, connection)

    monkeypatch.setattr(app.jobs, "assert_owner", check)
    async with app.jobs.heartbeat(job, owner):
        await asyncio.sleep(0.05)
    assert observed


async def test_branch_takeover_after_preflight_cannot_change_state(tmp_path):
    app = app_at(tmp_path)
    _, job, owner = seed_branch(app)

    def guard(connection=None):
        app.jobs.assert_owner(job, owner, connection)
        if connection is None:
            take_over(app, job)

    with pytest.raises(RuntimeError, match="lease"):
        await BranchRunner(app).run("B-000001", guard)
    assert app.db.one("SELECT status FROM branches")["status"] == "QUEUED"
    assert not app.db.query("SELECT * FROM probes")
    assert not app.gateway.inputs


@pytest.mark.parametrize("checkpoint", range(2, 8))
async def test_each_branch_checkpoint_rechecks_owner_before_mutation(tmp_path, checkpoint):
    app = app_at(tmp_path)
    _, job, owner = seed_branch(app)
    app.gateway.script = {
        "probe_manager": [formulation(), assessment("PROVED", "CONFIRM")],
        "solver": [solver("PROVED")],
    }
    preflights = 0
    snapshot = None

    def state():
        return {
            table: app.db.query(f"SELECT * FROM {table} ORDER BY id")
            for table in ("branches", "probes", "reports", "state_events")
        }

    def guard(connection=None):
        nonlocal preflights, snapshot
        app.jobs.assert_owner(job, owner, connection)
        if connection is None:
            preflights += 1
            if preflights == checkpoint:
                take_over(app, job)
                snapshot = state()

    with pytest.raises(RuntimeError, match="lease"):
        await BranchRunner(app).run("B-000001", guard)
    assert snapshot is not None
    assert state() == snapshot


@pytest.mark.parametrize("checkpoint", [1, 2])
async def test_brain_takeover_before_commit_preserves_snapshot(tmp_path, checkpoint):
    app = app_at(tmp_path)
    app.gateway.script["brain"] = [brain_output()]
    app.paths.atomic_write("report.md", "An edited report")
    app.db.execute(
        "INSERT INTO reports(public_id,kind,edited_path) VALUES('R-000001','CORRECTION','report.md')"
    )
    cycle = app.inbox.snapshot()
    job = app.db.one("SELECT id FROM jobs WHERE job_type='BRAIN'")["id"]
    owner = app.jobs.claim(job)
    preflights = 0

    def guard(connection=None):
        nonlocal preflights
        app.jobs.assert_owner(job, owner, connection)
        if connection is None:
            preflights += 1
            if preflights == checkpoint:
                take_over(app, job)

    with pytest.raises(RuntimeError, match="lease"):
        await BrainRunner(app).run(cycle, guard)
    assert app.db.one("SELECT status FROM brain_cycles")["status"] == (
        "PENDING" if checkpoint == 1 else "RUNNING"
    )
    assert app.db.one("SELECT processed_cycle_id FROM reports")["processed_cycle_id"] is None
    assert not app.db.query("SELECT * FROM insights")
    assert not app.db.query("SELECT * FROM branches")
    assert not app.db.query("SELECT * FROM cycle_artifacts")


def test_stale_owner_cannot_finalize_branch(tmp_path):
    app = app_at(tmp_path)
    branch, job, owner = seed_branch(app)
    take_over(app, job)

    def guard(connection=None):
        app.jobs.assert_owner(job, owner, connection)

    with pytest.raises(RuntimeError, match="lease"):
        app.inbox.finalize_branch(
            branch, "CONFIRMED", {"raw_path": "raw.md", "edited_path": "edited.md"}, guard=guard
        )
    assert not app.db.query("SELECT * FROM reports")
    assert app.db.one("SELECT final_report_id FROM branches")["final_report_id"] is None


async def test_old_exception_does_not_fail_replacement_branch(tmp_path):
    app = app_at(tmp_path)
    _, job, _ = seed_branch(app)
    app.db.execute("UPDATE jobs SET status='QUEUED',lease_owner=NULL WHERE id=?", (job,))

    async def lose_lease_and_fail(request):
        take_over(app, job)
        app.db.execute("UPDATE branches SET status='WAITING_FOR_SOLVER'")
        raise RuntimeError("Old invocation failed")

    app.gateway.script["probe_manager"] = [lose_lease_and_fail]
    with pytest.raises(RuntimeError):
        await app.execute_job(job)
    assert app.db.one("SELECT status FROM jobs")["status"] == "RUNNING"
    assert app.db.one("SELECT status FROM branches")["status"] == "WAITING_FOR_SOLVER"
