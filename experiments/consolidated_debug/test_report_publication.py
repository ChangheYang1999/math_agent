"""Offline temporary publication fixture; no inference or real project mutation."""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("publication_harness", HERE / "run_live.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)

from repair_sections import repair_latest_sections  # noqa: E402

from math_research_agent.config import Config  # noqa: E402
from math_research_agent.scheduler import Scheduler  # noqa: E402
from math_research_agent.store import Store, encode  # noqa: E402
from math_research_agent.transport import ScriptedTransport  # noqa: E402


def test_section_deferral_at_six_pairs_and_append_only_latest_repair(tmp_path):
    store = Store.initialize(
        tmp_path / "project", live.FLAG + ". Prove a finite identity.", Config(transport="fake")
    )
    rounds = []
    for _ in range(7):
        round_id = store.create_round(
            "root",
            "Prove this finite sum identity with explicit boundary checks and explain all equality cases.",
        )
        store.execute("UPDATE rounds SET stage='RESPONDED',report='{}' WHERE id=?", (round_id,))
        rounds.append(round_id)
    for first, following in zip(rounds, rounds[1:], strict=False):
        store.execute(
            "INSERT INTO parent_responses(round_id,parent_id,payload,next_round_id) VALUES(?,'root','{}',?)",
            (first, following),
        )
    updates = []
    for job_id, body in [
        ("z-original", "Earlier model-proposed finite-sum result."),
        ("a-final", "Latest model-proposed finite-sum result and final audit."),
    ]:
        payload = {
            "node_id": "root",
            "body": body,
            "claim_status": "MODEL_PROPOSED",
            "significant": True,
            "evidence_reference": job_id,
            "independent_verification": "",
        }
        store.execute(
            "INSERT INTO optional_jobs(id,priority,kind,actor_id,payload) VALUES(?,1,'section','root',?)",
            (job_id, encode(payload)),
        )
        updates.append(payload)
    scheduler = live.BoundedProScheduler(store, ScriptedTransport(store))
    for job in store.query("SELECT * FROM optional_jobs ORDER BY rowid"):
        scheduler._local_optional(job)
    assert {r["status"] for r in store.query("SELECT status FROM optional_jobs")} == {
        "DEFERRED_UNTIL_SIX_PAIRS"
    }
    assert not store.query("SELECT * FROM sections")
    for job in store.query("SELECT * FROM optional_jobs ORDER BY rowid"):
        Scheduler._local_optional(scheduler, job)
    assert (
        store.one("SELECT body FROM sections ORDER BY version DESC LIMIT 1")["body"]
        == updates[-1]["body"]
    )
    # Reproduce the observed stale publication without altering saved job order.
    store.update_section("root", updates[0])
    old_sections = store.query("SELECT * FROM sections ORDER BY id")
    old_parents = store.query("SELECT * FROM parent_responses ORDER BY rowid")
    result = repair_latest_sections(store, tmp_path / "before_repair.db")
    assert result["changed_nodes"] == ["root"] and result["new_inference_requests"] == 0
    assert (tmp_path / "before_repair.db").is_file()
    assert store.query("SELECT * FROM sections ORDER BY id")[:-1] == old_sections
    assert store.query("SELECT * FROM parent_responses ORDER BY rowid") == old_parents
    assert (
        store.one("SELECT body FROM sections ORDER BY version DESC LIMIT 1")["body"]
        == updates[-1]["body"]
    )
    before_repeat = store.query("SELECT * FROM events ORDER BY id")
    assert repair_latest_sections(store, tmp_path / "unused.db")["already_current"]
    assert store.query("SELECT * FROM events ORDER BY id") == before_repeat
    assert not (tmp_path / "unused.db").exists()
