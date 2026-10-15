"""Measurement/dispatch-guard checks only; none represent a live browser test."""

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

from math_research_agent.config import Config
from math_research_agent.store import Store

spec = spec_from_file_location("live_experiment", Path(__file__).with_name("run_experiment.py"))
runner = module_from_spec(spec)
spec.loader.exec_module(runner)
BASE = 1_800_000_000


def wall(seconds):
    return datetime.fromtimestamp(BASE + seconds, UTC).isoformat()


def timing():
    return {label: {"dispatch_started": {"at": wall(0)},
                    "terminal_record_received": {"at": wall(10)}} for label in "ABC"}


def sample(times):
    return {"tabs": [
        {"request_id": label, "observed_at": (BASE + at) * 1000,
         "fresh": True, "own_request": True, "generation": {"state": "active"}}
        for label, at in times.items()
    ]}


def test_cached_and_serial_activity_do_not_establish_concurrency():
    cached = [sample(dict.fromkeys("ABC", 1))] * 3
    assert runner.generation_overlap(cached, set("ABC"), timing(), {})["observed_overlap_seconds"] == 0
    serial = [sample({"A": 1, "B": 3, "C": 5}), sample({"A": 2, "B": 4, "C": 6})]
    assert runner.generation_overlap(serial, set("ABC"), timing(), {})["observed_overlap_seconds"] == 0


def test_overlap_requires_request_scoped_activity_inside_terminal_bounds():
    observations = [sample({"A": 1, "B": 1.1, "C": 1.2}),
                    sample({"A": 2, "B": 2.1, "C": 2.2})]
    result = runner.generation_overlap(observations, set("ABC"), timing(), {})
    assert result["observed_overlap_seconds"] == pytest.approx(.8, abs=1e-5)
    bounded = runner.generation_overlap(observations, set("ABC"), timing(), {"A": wall(1.5)})
    assert bounded["observed_overlap_seconds"] == 0
    assert "inferred" in result["limitation"]


def test_two_request_probe_refuses_ambiguous_or_uncertain_delivery():
    harness = object.__new__(runner.Harness)
    harness.data = {"attempts": {
        f"parallel-{label}-proof": {
            "request_id": label, "upstream_status": "completed", "terminal_status": "COMPLETED"
        } for label in "ABC"
    }}
    with pytest.raises(ValueError, match="No explicit authoritative capacity"):
        harness.confirmed_capacity_failure()
    failed = harness.data["attempts"]["parallel-C-proof"]
    failed.update(upstream_status="failed", terminal_status="ERROR_OR_UNCERTAIN",
                  upstream_error={"code": "RATE_LIMIT_EXCEEDED", "message": "Rate limit exceeded"})
    assert harness.confirmed_capacity_failure() == ["C"]
    failed["upstream_status"] = "running"
    with pytest.raises(ValueError, match="authoritatively terminal"):
        harness.confirmed_capacity_failure()


def test_exact_model_label_is_saved_without_changing_production_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "BASE", tmp_path)
    args = SimpleNamespace(run="exact-model", browser_instance=None, actual_model_label="GPT-6")
    harness = runner.Harness(args)
    assert harness.data["actual_model_label"] == "GPT-6"
    assert harness.bridge("smoke").store.config.bridge_parent_model == "GPT-6"
    assert Config().bridge_parent_model == "GPT-6 Thinking"
    assert runner.Harness(args).data["actual_model_label"] == "GPT-6"
    args.actual_model_label = "GPT-6 Thinking"
    with pytest.raises(ValueError, match="not permitted on resume"):
        runner.Harness(args)


async def test_tree_bounds_precede_dispatch_and_optional_controls_stay_deferred(tmp_path):
    store = Store.initialize(tmp_path, "Prove the odd-number identity rigorously.", Config())
    round_id = store.create_round("root", "Prove for every positive integer n that the sum of its first n positive odd integers is n squared, including n=1.")
    store.execute("UPDATE rounds SET number=2 WHERE id=?", (round_id,))
    scheduler = runner.ExperimentScheduler(store)
    scheduler.experiment_rounds_per_leaf = 1
    scheduler.experiment_nodes = {"root"}
    with pytest.raises(ValueError, match="dispatch bound"):
        await scheduler._leaf(round_id)
    assert store.query("SELECT * FROM turns") == []
    with pytest.raises(ValueError, match="topology is frozen"):
        await scheduler._session("unprepared-node", runner.COORDINATOR_MODEL)
    store.execute("INSERT INTO optional_jobs(id,priority,kind,actor_id,payload) VALUES('control',1,'tree','root','{}')")
    scheduler._local_optional(store.one("SELECT * FROM optional_jobs WHERE id='control'"))
    assert store.one("SELECT status FROM optional_jobs WHERE id='control'")["status"] == "DEFERRED_EXPERIMENT"
    assert store.node("root")["status"] == "ACTIVE"
