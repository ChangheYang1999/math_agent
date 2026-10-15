import asyncio

from fixtures.scripted import ScriptGateway, assessment, formulation, solver

from math_research_agent.config import Config
from math_research_agent.db import Database
from math_research_agent.orchestrator import Orchestrator
from math_research_agent.paths import Paths


def research(tmp_path, script, rounds=3):
    db = Database.initialize(tmp_path, "test", "Test")
    config = Config(limits={"max_probe_rounds": rounds})
    gw = ScriptGateway(script)
    app = Orchestrator(db, Paths(tmp_path), config, gw)
    return app, gw


def seed(app, n=1):
    for i in range(1, n + 1):
        insight = app.db.execute(
            "INSERT INTO insights(public_id,summary,status) VALUES(?,?,?)",
            (f"I-{i:06}", "Human supplied insight", "ACTIVE"),
        )
        app.db.execute(
            "INSERT INTO branches(public_id,parent_insight_id,status) VALUES(?,?,?)",
            (f"B-{i:06}", insight, "QUEUED"),
        )
        app.jobs.enqueue("RUN_BRANCH", "branch", f"B-{i:06}")


async def test_reformulation_disproof_and_edited_context(tmp_path):
    app, gw = research(
        tmp_path,
        {
            "probe_manager": [
                formulation(),
                assessment("INCONCLUSIVE", "REFORMULATE", formulation("Is every real x positive?")),
                assessment("DISPROVED", "REFUTE"),
            ],
            "solver": [solver("INCONCLUSIVE"), solver("DISPROVED")],
        },
    )
    seed(app)
    await app.workers()
    assert app.db.one("SELECT status FROM branches")["status"] == "REFUTED"
    assert [r["verdict"] for r in app.db.query("SELECT * FROM probes ORDER BY id")] == [
        "INCONCLUSIVE",
        "DISPROVED",
    ]
    assert len(app.db.query("SELECT * FROM reports WHERE processed_cycle_id IS NULL")) == 1
    assert app.paths.resolve("branches/B-000001/FINAL_REPORT.md").exists()
    final_report = app.paths.read("branches/B-000001/FINAL_REPORT.md")
    assert "I-000001" in final_report
    assert "branches/B-000001/Q-000001.2/solver_report.md" in final_report
    for request in gw.inputs:
        if request["role"] == "solver":
            assert "REDUNDANT" not in request["input_text"]
            assert "Human supplied insight" not in request["input_text"]
    assert all(
        a["editor_mode"] == "proof_safe"
        for a in app.db.query("SELECT * FROM artifacts WHERE kind='solver'")
    )
    assert len(app.db.query("SELECT * FROM state_events")) >= 5


async def test_max_rounds_forces_too_hard(tmp_path):
    app, _ = research(
        tmp_path,
        {
            "probe_manager": [
                formulation(),
                assessment("INCONCLUSIVE", "REFORMULATE", formulation()),
            ],
            "solver": [solver("INCONCLUSIVE")],
        },
        rounds=1,
    )
    seed(app)
    await app.workers()
    assert app.db.one("SELECT status FROM branches")["status"] == "TOO_HARD"
    assert len(app.db.query("SELECT * FROM probes")) == 1
    assert "round limit" in app.paths.read("branches/B-000001/FINAL_REPORT.md")


async def test_independent_failure_and_concurrency(tmp_path):
    active = 0
    peak = 0

    async def delayed(kw):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.03)
        active -= 1
        return solver("PROVED")

    script = {}
    for i in (1, 2, 3):
        prefix = f"branch:B-{i:06}"
        script[prefix + ":formulate"] = [formulation()]
        script[prefix + ":solve:1"] = [RuntimeError("network") if i == 2 else delayed]
        script[prefix + ":assess:1"] = [assessment("PROVED", "CONFIRM")]
    app, _ = research(tmp_path, script)
    seed(app, 3)
    await app.workers(max_concurrent=2)
    assert [r["status"] for r in app.db.query("SELECT * FROM branches ORDER BY id")] == [
        "CONFIRMED",
        "FAILED",
        "CONFIRMED",
    ]
    assert peak <= 2
    assert len(app.db.query("SELECT * FROM reports")) == 2


async def test_editor_failure_then_retry_reuses_solver(tmp_path):
    app, gw = research(
        tmp_path,
        {
            "probe_manager": [formulation(), assessment("PROVED", "CONFIRM")],
            "solver": [solver("PROVED")],
        },
    )
    seed(app)
    original = gw.run_structured

    async def fail_solver_editor(**kw):
        import json

        if kw["role"] == "editor" and json.loads(kw["input_text"])["kind"] == "solver":
            raise RuntimeError("Editor offline")
        return await original(**kw)

    gw.run_structured = fail_solver_editor
    await app.workers()
    row = app.db.one("SELECT * FROM artifacts WHERE kind='solver'")
    assert row["status"] == "EDIT_FAILED"
    assert app.paths.resolve(row["raw_path"]).exists()
    assert not app.paths.resolve(row["destination"]).exists()
    assert not app.db.query("SELECT * FROM reports")
    assert app.db.one("SELECT verdict FROM probes")["verdict"] == "PROVED"
    job = app.db.one("SELECT * FROM jobs WHERE job_type='RUN_BRANCH'")
    gw.run_structured = original
    await app.retry(job["id"])
    assert app.db.one("SELECT status FROM branches")["status"] == "CONFIRMED"
    assert len([x for x in gw.inputs if x["role"] == "solver"]) == 1
    assert len(app.db.query("SELECT * FROM probes")) == 1
