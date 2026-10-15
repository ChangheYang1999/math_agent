import json

import pytest
from fixtures.scripted import ScriptGateway, brain_output

from math_research_agent.config import Config
from math_research_agent.db import Database
from math_research_agent.orchestrator import Orchestrator
from math_research_agent.paths import Paths


def setup_research(tmp_path, script):
    db = Database.initialize(tmp_path, "test", "Test")
    paths = Paths(tmp_path)
    paths.atomic_write("problem/specification.md", "Human fixture: local sign problem")
    return Orchestrator(db, paths, Config(), ScriptGateway(script))


def report(app, number):
    path = f"reports/inbox/R-{number:06}.md"
    app.paths.atomic_write(path, f"Report {number}")
    app.db.execute(
        "INSERT INTO reports(id,public_id,kind,edited_path) VALUES(?,?,'CORRECTION',?)",
        (number, f"R-{number:06}", path),
    )


async def test_exact_checkpoint_race_101_to_107(tmp_path):
    app = setup_research(tmp_path, {})
    app.db.execute(
        "INSERT INTO brain_cycles(cycle_number,status,snapshot_report_id) VALUES(7,'COMPLETED',100)"
    )
    report(app, 100)
    app.db.execute("UPDATE reports SET processed_cycle_id=1 WHERE id=100")
    for n in range(101, 106):
        report(app, n)

    async def running(kw):
        context = json.loads(kw["input_text"])
        assert [x["report_id"] for x in context["reports"]] == [
            f"R-{n:06}" for n in range(101, 106)
        ]
        assert context["cycle"]["snapshot_report_id"] == 105
        with pytest.raises(ValueError, match="already"):
            await app.brain()
        report(app, 106)
        report(app, 107)
        output = brain_output(False)
        output["insight_updates"] = []
        return output

    empty = brain_output(False)
    empty["insight_updates"] = []
    app.gateway.script["brain"] = [running, empty]
    await app.brain()
    assert [
        r["id"] for r in app.db.query("SELECT id FROM reports WHERE processed_cycle_id=2")
    ] == list(range(101, 106))
    assert [
        r["id"] for r in app.db.query("SELECT id FROM reports WHERE processed_cycle_id IS NULL")
    ] == [106, 107]
    await app.brain()
    assert [r["id"] for r in app.db.query("SELECT id FROM reports WHERE processed_cycle_id=3")] == [
        106,
        107,
    ]
    assert not app.db.query("SELECT id FROM reports WHERE processed_cycle_id IS NULL")


async def test_brain_editor_failure_no_partial_state_and_retry(tmp_path):
    app = setup_research(tmp_path, {"brain": [brain_output()], "editor": [RuntimeError("offline")]})
    report(app, 1)
    with pytest.raises(Exception, match="Editing failed"):
        await app.brain()
    assert not app.db.query("SELECT * FROM insights")
    assert not app.db.query("SELECT * FROM branches")
    assert app.db.one("SELECT processed_cycle_id FROM reports")["processed_cycle_id"] is None
    assert not app.paths.resolve("strategy/CURRENT_STRATEGY.md").exists()
    job = app.db.one("SELECT * FROM jobs WHERE job_type='BRAIN'")
    await app.retry(job["id"])
    assert len(app.db.query("SELECT * FROM branches")) == 2
    assert app.db.one("SELECT processed_cycle_id FROM reports")["processed_cycle_id"] == 1
    assert app.paths.resolve("strategy/CURRENT_STRATEGY.md").exists()
    assert len([x for x in app.gateway.inputs if x["role"] == "brain"]) == 1


async def test_invalid_parent_retried_with_feedback_and_limits_enforced(tmp_path):
    bad = brain_output()
    bad["branch_proposals"][0]["new_insight_index"] = 99
    app = setup_research(tmp_path, {"brain": [bad, brain_output()]})
    app.config.limits.max_new_branches_per_brain_cycle = 1
    await app.brain()
    assert len(app.db.query("SELECT * FROM branches")) == 1
    assert len([x for x in app.gateway.inputs if x["role"] == "brain"]) == 2
    assert (
        "validation_feedback"
        in [x for x in app.gateway.inputs if x["role"] == "brain"][1]["input_text"]
    )
