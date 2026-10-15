"""Mandatory deterministic two-cycle research simulation with production FakeModelGateway."""

import json

from fixtures.scripted import assessment, background_output, brain_output, formulation, solver

from math_research_agent.config import Config
from math_research_agent.db import Database
from math_research_agent.model_gateway import FakeModelGateway
from math_research_agent.orchestrator import Orchestrator
from math_research_agent.paths import Paths


async def test_full_fake_research_program_survives_reopen(tmp_path):
    root = Orchestrator.initialize(tmp_path, "sign-research", "Sign research")
    paths = Paths(root)
    config = Config(runtime={"retry_base_seconds": 0})
    db = Database(root / "state.db")
    initial = FakeModelGateway(
        db, paths, config, {"background": [background_output()], "brain": [brain_output()]}
    )
    app = Orchestrator(db, paths, config, initial)
    app.set_problem("Which real expressions have a definite sign?")
    await app.background()
    await app.brain()
    assert [r["public_id"] for r in db.query("SELECT * FROM insights ORDER BY id")] == [
        "I-000001",
        "I-000002",
    ]
    assert len(db.query("SELECT * FROM branches WHERE status='QUEUED'")) == 2
    # New service/gateway instances model a later CLI process.
    db = Database(root / "state.db")
    script = {
        "branch:B-000001:formulate": [formulation()],
        "branch:B-000001:solve:1": [solver("INCONCLUSIVE")],
        "branch:B-000001:assess:1": [assessment("INCONCLUSIVE", "REFORMULATE", formulation())],
        "branch:B-000001:solve:2": [solver("PROVED")],
        "branch:B-000001:assess:2": [assessment("PROVED", "CONFIRM")],
        "branch:B-000002:formulate": [formulation("Is every real x positive?")],
        "branch:B-000002:solve:1": [solver("DISPROVED")],
        "branch:B-000002:assess:1": [assessment("DISPROVED", "REFUTE")],
        "brain": [brain_output(False)],
    }
    app = Orchestrator(db, paths, config, FakeModelGateway(db, paths, config, script))
    results = await app.workers(max_concurrent=2)
    assert all(r["error"] is None for r in results)
    assert [r["status"] for r in db.query("SELECT * FROM branches ORDER BY id")] == [
        "CONFIRMED",
        "REFUTED",
    ]
    assert len(db.query("SELECT * FROM reports WHERE processed_cycle_id IS NULL")) == 2
    await app.brain()
    assert [r["status"] for r in db.query("SELECT * FROM insights ORDER BY id")] == [
        "STRENGTHENED",
        "REFUTED",
    ]
    assert not db.query("SELECT * FROM reports WHERE processed_cycle_id IS NULL")
    assert len(db.query("SELECT * FROM brain_cycles WHERE status='COMPLETED'")) == 2
    assert "reject positivity of all reals" in paths.read("strategy/CURRENT_STRATEGY.md")
    assert "I-000002" in paths.read("strategy/INSIGHT_LOG.md")
    artifacts = db.query("SELECT * FROM artifacts")
    assert len(artifacts) > 20
    for artifact in artifacts:
        assert paths.resolve(artifact["raw_path"]).is_file()
        assert paths.resolve(artifact["edited_path"]).is_file()
    proof = db.one("SELECT * FROM artifacts WHERE kind='solver' AND scope_id='Q-000001.2'")
    assert proof["editor_mode"] == "proof_safe"
    assert "REDUNDANT" in paths.read(proof["raw_path"])
    assert "REDUNDANT" not in paths.read(proof["edited_path"])
    run = db.one("SELECT * FROM model_runs WHERE id=?", (proof["model_run_id"],))
    assert json.loads(paths.read(run["raw_output_path"]))["verdict"] == "PROVED"
    assert run["prompt_hash"] and paths.resolve(run["prompt_path"]).is_file()
    # Correction is new human evidence, and cannot change the historical Solver verdict.
    correction = app.add_correction("Human audit: check the exact sign assumptions.", "I-000001")
    assert correction == "R-000003"
    assert app.status()["inbox_count"] == 1
    assert db.one("SELECT verdict FROM probes WHERE public_id='Q-000001.2'")["verdict"] == "PROVED"
    # Strategic snapshots can repair accidental deletion of materialized files.
    paths.resolve("strategy/CURRENT_STRATEGY.md").unlink()
    app.reconcile()
    assert "Retain square positivity" in paths.read("strategy/CURRENT_STRATEGY.md")
